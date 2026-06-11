import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple

import networkx as nx

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.lib import hub
from ryu.lib.packet import arp, ethernet, ipv4, packet, udp
from ryu.ofproto import ofproto_v1_3
from ryu.topology import event
from ryu.topology.api import get_link


ETH_TYPE_IP = 0x0800
ETH_TYPE_ARP = 0x0806
ETH_TYPE_MPLS = 0x8847

PRIO_UDP = 1000
PRIO_ICMP = 500
PRIO_MISS = 0

INTERVAL = 5.0

LOGS_DIR = "results/single_path/logs"
os.makedirs(LOGS_DIR, exist_ok=True)


class SinglePathController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super(SinglePathController, self).__init__(*args, **kwargs)
        self.datapaths: Dict[int, Any] = {}  # {dpid: datapath}
        self.hosts: Dict[str, Tuple[int, int, str]] = {}  # {ip: (dpid, port, mac)}
        self.neigh: Dict[int, Dict[int, int]] = {}  # {dpid: {neighbor_dpid: port}}
        self.net = nx.Graph()

        self.port_stats: Dict[
            Tuple[int, int], Tuple[int, int]
        ] = {}  # {(dpid, port_no): (total, now)}
        self.link_stats: Dict[
            Tuple[int, int], Dict[str, float | str]
        ] = {}  # {(src, dst): {'state': 'NORM', 'throughput_bps': 0.0}}

        self._installing: set = set()

        hub.spawn(self._monitor_stats)

        run_id = os.environ.get("RUN_ID") or str(int(time.time()))
        log_file = os.path.join(LOGS_DIR, f"stats_single_path_{run_id}.log")

        self.logger = logging.getLogger(f"single_path_{run_id}")
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False

        fh = logging.FileHandler(log_file, mode="w", encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s %(message)s"))

        self.logger.handlers.clear()
        self.logger.addHandler(fh)

    # -----------------------------------------------------------------------
    # Ryu event handlers
    # -----------------------------------------------------------------------

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev: ofp_event.EventOFPSwitchFeatures) -> None:
        msg = ev.msg
        dp = msg.datapath
        dpid = dp.id
        self.datapaths[dpid] = dp
        ofproto = dp.ofproto
        parser = dp.ofproto_parser

        self.logger.info(f"Switch connected, dpid: {dpid}")
        match = parser.OFPMatch()
        actions = [
            parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)
        ]
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        self._add_flow(
            dp=dp, table_id=0, priority=PRIO_MISS, match=match, instructions=inst
        )

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev: ofp_event.EventOFPPacketIn) -> None:
        msg = ev.msg
        dp = msg.datapath
        in_port = msg.match["in_port"]

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)
        if not eth:
            return

        arp_pkt = pkt.get_protocol(arp.arp)

        if arp_pkt:
            self._handle_arp(dp, in_port, eth, arp_pkt, msg)
            return

        ip_pkt = pkt.get_protocol(ipv4.ipv4)
        if ip_pkt:
            udp_pkt = pkt.get_protocol(udp.udp)

            if udp_pkt:
                if udp_pkt.dst_port < 10000:
                    return
                self._handle_udp(ip_pkt, udp_pkt, msg)
                return

            self._handle_ip(ip_pkt, msg)

    @set_ev_cls(event.EventSwitchEnter)
    @set_ev_cls(event.EventSwitchLeave)
    @set_ev_cls(event.EventLinkAdd)
    @set_ev_cls(event.EventLinkDelete)
    def topology_change_handler(self, ev: Any) -> None:
        new_neigh = {}
        new_net = nx.Graph()
        links = get_link(self, None)
        for link in links:
            src = link.src.dpid
            dst = link.dst.dpid
            src_port = link.src.port_no
            new_neigh.setdefault(src, {})[dst] = src_port
            new_net.add_edge(src, dst, weight=1)

        self.neigh = new_neigh
        self.net = new_net

    @set_ev_cls(ofp_event.EventOFPPortStatsReply, MAIN_DISPATCHER)
    def port_stats_reply_handler(self, ev: ofp_event.EventOFPPortStatsReply) -> None:
        msg = ev.msg
        dp = msg.datapath
        dpid = dp.id
        ofproto = dp.ofproto

        now = time.time()
        for stat in msg.body:
            port_no = stat.port_no
            if port_no > ofproto.OFPP_MAX:
                continue

            key = (dpid, port_no)
            total = stat.tx_bytes
            last = self.port_stats.get(key)
            self.port_stats[key] = (total, now)

            if last is None:
                continue

            prev_bytes, prev_time = last
            dt = now - prev_time
            dbytes = total - prev_bytes

            if dt < 0.1 or dbytes <= 0:
                continue

            throughput_mbps = (dbytes * 8.0) / (dt * 1e6)

            if throughput_mbps > 100000.0:
                continue

            self.logger.info(
                f"STATS dpid={dpid} port={port_no} "
                f"throughput={throughput_mbps:.3f} Mbps"
            )

    # -----------------------------------------------------------------------
    # ARP and Host Discovery
    # -----------------------------------------------------------------------

    def _handle_arp(
        self, dp: Any, in_port: int, eth: Any, arp_pkt: Any, msg: Any
    ) -> None:
        src_ip = arp_pkt.src_ip
        dst_ip = arp_pkt.dst_ip
        dpid = dp.id

        if src_ip not in self.hosts:
            self.hosts[src_ip] = (dpid, in_port, eth.src)
            self.logger.info(
                f"Host discovered: {src_ip}, MAC: {eth.src} at dpid={dpid} port={in_port}"
            )

        if dst_ip in self.hosts:
            _, _, dst_mac = self.hosts[dst_ip]

            self._send_arp_reply(
                dp=dp,
                out_port=in_port,
                target_mac=eth.src,
                target_ip=src_ip,
                sender_mac=dst_mac,
                sender_ip=dst_ip,
            )
        else:
            self._flood_to_edge_ports(msg)

    def _flood_to_edge_ports(self, msg: Any) -> None:
        data = msg.data
        for dpid, dp in self.datapaths.items():
            ofproto = dp.ofproto
            parser = dp.ofproto_parser

            neighbor_ports = self.neigh.get(dpid, {}).values()

            actions = []
            for port_no in dp.ports:
                if port_no <= ofproto.OFPP_MAX and port_no not in neighbor_ports:
                    if dpid == msg.datapath.id and port_no == msg.match["in_port"]:
                        continue
                    actions.append(parser.OFPActionOutput(port_no))

            if actions:
                out = parser.OFPPacketOut(
                    datapath=dp,
                    buffer_id=ofproto.OFP_NO_BUFFER,
                    in_port=ofproto.OFPP_CONTROLLER,
                    actions=actions,
                    data=data,
                )
                dp.send_msg(out)

    def _send_arp_reply(
        self,
        dp: Any,
        out_port: int,
        target_mac: str,
        target_ip: str,
        sender_mac: str,
        sender_ip: str,
    ) -> None:
        ofproto = dp.ofproto
        parser = dp.ofproto_parser

        pkt = packet.Packet()
        pkt.add_protocol(
            ethernet.ethernet(ethertype=ETH_TYPE_ARP, dst=target_mac, src=sender_mac)
        )
        pkt.add_protocol(
            arp.arp(
                opcode=arp.ARP_REPLY,
                src_mac=sender_mac,
                src_ip=sender_ip,
                dst_mac=target_mac,
                dst_ip=target_ip,
            )
        )
        pkt.serialize()

        actions = [parser.OFPActionOutput(out_port)]
        out = parser.OFPPacketOut(
            datapath=dp,
            buffer_id=ofproto.OFP_NO_BUFFER,
            in_port=ofproto.OFPP_CONTROLLER,
            actions=actions,
            data=pkt.data,
        )

        dp.send_msg(out)

    # -----------------------------------------------------------------------
    # Path Calculation and Flow Installation
    # -----------------------------------------------------------------------

    def _calculate_path(self, src: int, dst: int) -> Optional[List[int]]:
        try:
            return nx.shortest_path(self.net, src, dst, weight="weight")
        except nx.NetworkXNoPath:
            return None

    def _handle_ip(self, ip_pkt: ipv4.ipv4, msg: Any) -> None:
        src_ip = ip_pkt.src
        dst_ip = ip_pkt.dst

        if src_ip not in self.hosts or dst_ip not in self.hosts:
            return

        key = (src_ip, dst_ip)
        if key in self._installing:
            return
        self._installing.add(key)

        src_dpid, src_port, _ = self.hosts[src_ip]
        dst_dpid, dst_port, _ = self.hosts[dst_ip]

        path = self._calculate_path(src_dpid, dst_dpid)
        if not path:
            self._installing.discard(key)
            return

        self._install_icmp_path(path, src_ip, dst_ip, dst_port)

        reverse_key = (dst_ip, src_ip)
        if reverse_key not in self._installing:
            self._installing.add(reverse_key)
            reverse_path = list(reversed(path))
            self._install_icmp_path(reverse_path, dst_ip, src_ip, src_port)

        self._forward_packet(msg, path, dst_port)

    def _handle_udp(self, ip_pkt: ipv4.ipv4, udp_pkt: udp.udp, msg: Any) -> None:
        src_ip = ip_pkt.src
        dst_ip = ip_pkt.dst
        src_udp = udp_pkt.src_port
        dst_udp = udp_pkt.dst_port

        if src_ip not in self.hosts or dst_ip not in self.hosts:
            return

        key = (src_ip, dst_ip, dst_udp)
        if key in self._installing:
            src_dpid, _, _ = self.hosts[src_ip]
            dst_dpid, dst_port, _ = self.hosts[dst_ip]
            path = self._calculate_path(src_dpid, dst_dpid)
            if path:
                self._forward_packet(msg, path, dst_port)
            return

        self._installing.add(key)

        try:
            src_dpid, _, _ = self.hosts[src_ip]
            dst_dpid, dst_port, _ = self.hosts[dst_ip]

            path = self._calculate_path(src_dpid, dst_dpid)
            if not path:
                return

            self._install_udp_path(path, src_ip, dst_ip, src_udp, dst_udp, dst_port)
            self._forward_packet(msg, path, dst_port)
            hub.spawn_after(0.5, self._remove_from_installing, key)
        except Exception as e:
            self.logger.error(f"Error: {e}")
            self._installing.discard(key)

    def _remove_from_installing(self, key: tuple) -> None:
        self._installing.discard(key)

    # -----------------------------------------------------------------------
    # Packet forwarding
    # -----------------------------------------------------------------------

    def _forward_packet(self, msg: Any, path: List[int], final_port: int) -> None:
        dp = msg.datapath
        dpid = dp.id
        parser = dp.ofproto_parser

        if dpid not in path:
            return

        i = path.index(dpid)

        if i < len(path) - 1:
            next_dpid = path[i + 1]
            out_port = self.neigh.get(dpid, {}).get(next_dpid)
        else:
            out_port = final_port

        if out_port is None:
            return

        data = None
        if msg.buffer_id == dp.ofproto.OFP_NO_BUFFER:
            data = msg.data

        actions = [parser.OFPActionOutput(out_port)]
        out = parser.OFPPacketOut(
            datapath=dp,
            buffer_id=msg.buffer_id,
            in_port=msg.match["in_port"],
            actions=actions,
            data=data,
        )
        dp.send_msg(out)

    # -----------------------------------------------------------------------
    # Flow installation
    # -----------------------------------------------------------------------

    def _install_icmp_path(
        self, path: List[int], src_ip: str, dst_ip: str, final_port: int
    ) -> None:
        for i in range(len(path) - 1, -1, -1):
            dpid = path[i]
            dp = self.datapaths[dpid]
            ofproto = dp.ofproto
            parser = dp.ofproto_parser

            if i < len(path) - 1:
                out_port = self.neigh[dpid][path[i + 1]]
            else:
                out_port = final_port

            match = parser.OFPMatch(
                eth_type=ETH_TYPE_IP, ipv4_src=src_ip, ipv4_dst=dst_ip, ip_proto=1
            )
            actions = [parser.OFPActionOutput(out_port)]
            inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]

            self._add_flow(
                dp=dp, table_id=0, priority=PRIO_ICMP, match=match, instructions=inst
            )

    def _install_udp_path(
        self,
        path: List[int],
        src_ip: str,
        dst_ip: str,
        src_port: int,
        dst_port: int,
        final_port: int,
    ) -> None:
        self.logger.info(
            f"Installing path {src_ip} -> {dst_ip} port {dst_port}: {path}"
        )
        for i in range(len(path) - 1, -1, -1):
            dpid = path[i]
            dp = self.datapaths[dpid]
            ofproto = dp.ofproto
            parser = dp.ofproto_parser

            if i < len(path) - 1:
                out_port = self.neigh[dpid][path[i + 1]]
            else:
                out_port = final_port

            match = parser.OFPMatch(
                eth_type=ETH_TYPE_IP,
                ipv4_src=src_ip,
                ipv4_dst=dst_ip,
                ip_proto=17,
                udp_dst=dst_port,
            )
            actions = [parser.OFPActionOutput(out_port)]
            inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]

            self._add_flow(
                dp=dp,
                table_id=0,
                priority=PRIO_UDP,
                match=match,
                instructions=inst,
                idle_timeout=3,
            )

    def _add_flow(
        self,
        dp: Any,
        table_id: int,
        priority: int,
        match: Any,
        instructions: List,
        idle_timeout: int = 0,
    ) -> None:
        parser = dp.ofproto_parser
        mod = parser.OFPFlowMod(
            datapath=dp,
            table_id=table_id,
            idle_timeout=idle_timeout,
            priority=priority,
            match=match,
            instructions=instructions,
        )
        dp.send_msg(mod)

    # -----------------------------------------------------------------------
    # Network Monitoring and Link State
    # -----------------------------------------------------------------------

    def _monitor_stats(self) -> None:
        while True:
            for dp in self.datapaths.values():
                self._request_port_stats(dp)
            hub.sleep(INTERVAL)

    def _request_port_stats(self, dp: Any) -> None:
        ofproto = dp.ofproto
        parser = dp.ofproto_parser

        try:
            req = parser.OFPPortStatsRequest(dp, 0, ofproto.OFPP_ANY)
            dp.send_msg(req)
        except Exception as e:
            self.logger.exception(f"PortStatsRequest error: {e}")
