import heapq
import logging
import os
import time
from collections import defaultdict, deque
from typing import Any, DefaultDict, Deque, Dict, List, Optional, Set, Tuple

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.lib import hub
from ryu.lib.packet import arp, ethernet, packet
from ryu.ofproto import ofproto_v1_3
from ryu.topology import event
from ryu.topology.api import get_link


MAX_BW = 100.0
WARN_TH = 0.4 * MAX_BW
CONG_TH = 0.8 * MAX_BW
WEIGHTS = {"NORM": 1, "WARN": 1000, "CONG": 65535}
INTERVAL = 5.0
LABEL_REUSE_HIST = 5

ETH_TYPE_IP = 0x0800
ETH_TYPE_ARP = 0x0806
ETH_TYPE_MPLS = 0x8847

PRIO_MPLS = 1000
PRIO_ARP = 100
PRIO_POP = 500
PRIO_MISS = 0

LOGS_DIR = "results/mpls_cached/logs"
os.makedirs(LOGS_DIR, exist_ok=True)


class MplsControllerCached(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(MplsControllerCached, self).__init__(*args, **kwargs)
        self.topology_api_app = self
        self.datapaths: Dict[int, Any] = {}  # {dpid: datapath}
        self.neigh: Dict[int, Dict[int, int]] = {}  # {dpid: {neighbor_dpid: out_port}}
        self.hosts: Dict[
            str, Tuple[int, int, str]
        ] = {}  # {src_ip: (dpid, in_port, mac)}
        self.egress_pop_installed: Set[int] = set()
        self.path_cache: Dict[
            Tuple[int, int], Dict[str, Any]
        ] = {}  # {(src_dpid, dst_dpid): {"path": path, "label": label}}
        self.mpls_label: int = 100

        self.port_stats: Dict[
            Tuple[int, int], Tuple[int, int]
        ] = {}  # {(dpid, port_no): (total, now)}
        self.link_stats: Dict[
            Tuple[int, int], Dict[str, float | str]
        ] = {}  # {(src, dst): {'state': 'NORM', 'throughput_bps': 0.0}}

        self.label_refcount: Dict[int, int] = {}
        self.path_label_history: DefaultDict[
            int, Deque[Tuple[int, List[int]]]
        ] = defaultdict(lambda: deque(maxlen=LABEL_REUSE_HIST))
        self.label_to_path_info: Dict[int, Dict[str, Any]] = {}

        hub.spawn(self._monitor_stats)

        run_id = os.environ.get("RUN_ID") or str(int(time.time()))
        log_file = os.path.join(LOGS_DIR, f"stats_mpls_cached_{run_id}.log")

        self.logger = logging.getLogger(f"mpls_{run_id}")
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

        # Table 0: If the packet is MPLS (0x8847), process it here.
        # If it is IP (0x0800), send it to Table 1.
        match = parser.OFPMatch()
        inst = [parser.OFPInstructionGotoTable(1)]
        self._add_flow(
            dp=dp, table_id=0, priority=PRIO_MISS, match=match, instructions=inst
        )

        # If it is ARP (0x0806) send to controller (PacketIn)
        match = parser.OFPMatch(eth_type=ETH_TYPE_ARP)
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER)]
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        self._add_flow(
            dp=dp, table_id=0, priority=PRIO_ARP, match=match, instructions=inst
        )

        # Table-miss entry: send all unmatched packets to controller
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER)]
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        self._add_flow(
            dp=dp, table_id=1, priority=PRIO_MISS, match=match, instructions=inst
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

    @set_ev_cls(event.EventSwitchEnter)
    @set_ev_cls(event.EventSwitchLeave)
    @set_ev_cls(event.EventLinkAdd)
    @set_ev_cls(event.EventLinkDelete)
    def topology_change_handler(self, ev: Any) -> None:
        new_neigh = {}

        links = get_link(self, None)
        for link in links:
            src = link.src.dpid
            dst = link.dst.dpid
            src_port = link.src.port_no
            new_neigh.setdefault(src, {})[dst] = src_port

        if new_neigh == self.neigh or len(new_neigh) <= len(self.neigh):
            return
        self.neigh = new_neigh
        self._recalculate_paths()

    @set_ev_cls(ofp_event.EventOFPPortStatsReply, MAIN_DISPATCHER)
    def port_stats_reply_handler(self, ev: ofp_event.EventOFPPortStatsReply) -> None:
        msg = ev.msg
        dp = msg.datapath
        dpid = dp.id
        ofproto = dp.ofproto
        changed_links = []

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

            throughput_bps = (dbytes * 8.0) / dt

            throughput_mbps = throughput_bps / 1e6
            if throughput_mbps > 100000.0:
                continue

            self.logger.info(
                f"STATS dpid={dpid} port={port_no} "
                f"throughput={throughput_mbps:.3f} Mbps"
            )

            changed_links.extend(
                self._update_link_states(dpid, port_no, throughput_bps)
            )

        if changed_links:
            self._handle_link_changes(changed_links)

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

            if dpid not in self.egress_pop_installed:
                self._install_pe_pop(dpid, in_port)

            self._recalculate_paths()

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

    def _update_link_states(
        self, dpid: int, port_no: int, throughput_bps: float
    ) -> List[Tuple[int, int]]:
        changed_links = []

        for neighbor, out_port in self.neigh.get(dpid, {}).items():
            if out_port != port_no:
                continue

            link = (dpid, neighbor)

            old_state = self.link_stats.get(link, {}).get("state")
            new_state = self._classify_state(throughput_bps)

            self.link_stats[link] = {
                "state": new_state,
                "throughput_bps": throughput_bps,
            }

            if old_state != new_state:
                self.logger.info(
                    f"Link {dpid} -> {neighbor}: "
                    f"{old_state} -> {new_state} "
                    f"({throughput_bps / 1e6:.2f} Mbps)"
                )

                changed_links.append(link)

        return changed_links

    def _classify_state(self, throughput_bps: float) -> str:
        throughput_mbps = throughput_bps / 1e6
        if throughput_mbps >= CONG_TH:
            return "CONG"
        if throughput_mbps >= WARN_TH:
            return "WARN"
        return "NORM"

    def _handle_link_changes(self, changed_links: List[Tuple[int, int]]) -> None:
        if not self.path_cache:
            self._recalculate_paths()
            return

        affected_dsts = set()
        for link in changed_links:
            affected_dsts |= self._get_affected_dsts(link)

        if affected_dsts:
            self._recalculate_paths(affected_dsts)

    def _get_affected_dsts(self, link: Tuple[int, int]) -> Set[int]:
        u, v = link
        affected = set()

        for (_, dst), path_data in self.path_cache.items():
            path = path_data["path"]

            if self._path_uses_link(path, u, v):
                affected.add(dst)

        return affected

    def _path_uses_link(self, path: List[int], u: int, v: int) -> bool:
        for i in range(len(path) - 1):
            a, b = path[i], path[i + 1]

            if (a == u and b == v) or (a == v and b == u):
                return True

        return False

    # -----------------------------------------------------------------------
    # Path Calculation
    # -----------------------------------------------------------------------

    def _recalculate_paths(self, affected_dsts: Optional[Set[int]] = None) -> None:
        graph = self._build_reverse_graph()
        nodes = list(self.datapaths.keys())

        for dst_ip, (dst_dpid, _, _) in self.hosts.items():

            if affected_dsts and dst_dpid not in affected_dsts:
                continue

            parent = self._reverse_dijkstra(dst_dpid, graph, nodes)
            paths = self._build_paths(parent, dst_dpid)

            self._update_paths_for_destination(dst_ip, dst_dpid, paths)

    def _build_reverse_graph(self) -> Dict[int, List[Tuple[int, int]]]:
        reverse_graph = defaultdict(list)
        for u in self.neigh:
            for v, _ in self.neigh[u].items():
                link_info = self.link_stats.get((u, v), {"state": "NORM"})
                cost = WEIGHTS.get(link_info["state"], WEIGHTS["NORM"])
                reverse_graph[v].append((u, cost))
        return reverse_graph

    def _reverse_dijkstra(
        self,
        dst_dpid: int,
        reverse_graph: Dict[int, List[Tuple[int, int]]],
        nodes: List[int],
    ) -> Optional[Dict[int, int]]:
        distances = {node: float("inf") for node in nodes}
        parent = {node: None for node in nodes}

        distances[dst_dpid] = 0
        priority_queue = [(0, dst_dpid)]
        while priority_queue:
            current_cost, current_node = heapq.heappop(priority_queue)
            if current_cost > distances[current_node]:
                continue

            for neighbor, edge_cost in reverse_graph.get(current_node, []):
                new_cost = current_cost + edge_cost
                if new_cost < distances[neighbor]:
                    distances[neighbor] = new_cost
                    parent[neighbor] = current_node

                    heapq.heappush(
                        priority_queue,
                        (new_cost, neighbor),
                    )

        return parent

    def _build_paths(
        self,
        parent: Optional[Dict[int, int]],
        dst_dpid: int,
    ) -> Dict[int, List[int]]:
        paths = {}

        for src_dpid in parent:

            if src_dpid == dst_dpid:
                continue

            if parent[src_dpid] is None:
                continue

            path = []
            current = src_dpid

            while current is not None:
                path.append(current)

                if current == dst_dpid:
                    break

                current = parent[current]

            if path[-1] == dst_dpid:
                paths[src_dpid] = path

        return paths

    def _update_paths_for_destination(
        self,
        dst_ip: str,
        dst_dpid: int,
        paths: Dict[int, List[int]],
    ) -> None:
        for src_ip, (src_dpid, _, _) in self.hosts.items():

            if src_ip == dst_ip:
                continue

            path = paths.get(src_dpid)

            if not path:
                continue

            if not self._path_changed(src_dpid, dst_dpid, path):
                continue

            self._install_new_path(
                src_ip,
                dst_ip,
                src_dpid,
                dst_dpid,
                path,
            )

    def _path_changed(
        self,
        src_dpid: int,
        dst_dpid: int,
        new_path: List[int],
    ) -> bool:
        cached = self.path_cache.get((src_dpid, dst_dpid))

        if not cached:
            return True

        return cached["path"] != new_path

    def _install_new_path(
        self,
        src_ip: str,
        dst_ip: str,
        src_dpid: int,
        dst_dpid: int,
        path: List[int],
    ) -> None:
        stitch_node, reuse_label = self._find_reuseable_segment(path, dst_dpid)
        stitch_idx = path.index(stitch_node) if stitch_node else None

        if reuse_label is not None and stitch_node is None:
            self.logger.info(
                f"Full reuse of label {reuse_label} for {src_ip}->{dst_ip}: {path}"
            )
            self.path_cache[(src_dpid, dst_dpid)] = {
                "path": path,
                "label": reuse_label,
                "stitch_idx": None,
                "reuse_label": None,
            }
            self._install_pe_push(path, src_ip, dst_ip, reuse_label)
            return

        label = self.mpls_label
        self.mpls_label += 1

        self.path_cache[(src_dpid, dst_dpid)] = {
            "path": path,
            "label": label,
            "stitch_idx": stitch_idx,
            "reuse_label": reuse_label,
        }

        self.label_to_path_info[label] = {"path": path, "stitch_idx": stitch_idx}
        self.label_refcount[label] = 1

        self.logger.info(f"New path {src_ip}->{dst_ip}: {path}, MPLS label={label}")

        if stitch_node is not None:
            self.label_refcount[reuse_label] += 1
            self.logger.info(f"Reusing label {reuse_label} from node {stitch_node}")
            self._install_mpls_path_with_stitch(
                path, src_ip, dst_ip, label, stitch_idx, reuse_label
            )
        else:
            self._install_mpls_path(path, src_ip, dst_ip, label)

        if dst_dpid not in self.path_label_history:
            self.path_label_history[dst_dpid] = []

        if len(self.path_label_history[dst_dpid]) >= LABEL_REUSE_HIST:
            oldest_label, _ = self.path_label_history[dst_dpid].popleft()
            self._expire_old_path(oldest_label)

        self.path_label_history[dst_dpid].append((label, path))

    def _find_reuseable_segment(
        self, new_path: List[int], dst_dpid: int
    ) -> Tuple[Optional[int], Optional[int]]:
        best_len = 1
        best_stitch = None
        best_label = None

        for label, cand_path in self.path_label_history[dst_dpid]:
            if label not in self.label_refcount:
                continue

            cand_info = self.label_to_path_info.get(label)
            cand_stitch_idx = cand_info.get("stitch_idx") if cand_info else None

            ni = len(new_path) - 1
            ci = len(cand_path) - 1
            match_len = 0

            while ni >= 0 and ci >= 0 and new_path[ni] == cand_path[ci]:
                match_len += 1
                ni -= 1
                ci -= 1

            if match_len >= 2:
                stitch_idx = ni + 1
                cand_match_idx = ci + 1

                if cand_stitch_idx is not None and cand_match_idx >= cand_stitch_idx:
                    continue

                if stitch_idx == 0 and match_len > best_len:
                    best_len = match_len
                    best_stitch = None
                    best_label = label
                    continue

                if stitch_idx > 0 and match_len > best_len:
                    best_len = match_len
                    best_stitch = new_path[stitch_idx]
                    best_label = label

        return best_stitch, best_label

    def _expire_old_path(self, label: int) -> None:
        if label not in self.label_refcount:
            return

        self.label_refcount[label] -= 1
        label_info = self.label_to_path_info.get(label)
        reuse_label = label_info.get("reuse_label") if label_info else None

        if self.label_refcount[label] <= 0:
            if label_info:
                self.logger.info(
                    f"Label {label} refcount reached 0. Remove rules from switches."
                )
                self._expire_old_label(
                    label, label_info["path"], label_info["stitch_idx"]
                )
                del self.label_to_path_info[label]
            del self.label_refcount[label]

            if reuse_label is not None:
                self.logger.info(
                    f"Decrementing parent reuse_label {reuse_label} due to loss of child route."
                )
                self._expire_old_path(reuse_label)

    # -----------------------------------------------------------------------
    # Flow installation
    # -----------------------------------------------------------------------

    def _install_mpls_path(
        self, path: List[int], src_ip: str, dst_ip: str, label: int
    ) -> None:
        for i in range(len(path) - 2, 0, -1):
            self._install_p_forward(path, i, label)
        self._install_pe_push(path, src_ip, dst_ip, label)

    def _install_mpls_path_with_stitch(
        self,
        path: List[int],
        src_ip: str,
        dst_ip: str,
        new_label: int,
        stitch_idx: int,
        reuse_label: int,
    ) -> None:
        # Stitch node
        dpid = path[stitch_idx]
        dp = self.datapaths[dpid]
        ofproto = dp.ofproto
        parser = dp.ofproto_parser
        match = parser.OFPMatch(eth_type=ETH_TYPE_MPLS, mpls_label=new_label)
        actions = [
            parser.OFPActionSetField(mpls_label=reuse_label),
            parser.OFPActionOutput(self.neigh[dpid][path[stitch_idx + 1]]),
        ]
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        self._add_flow(
            dp=dp, table_id=0, priority=PRIO_MPLS, match=match, instructions=inst
        )

        for i in range(stitch_idx - 1, 0, -1):
            self._install_p_forward(path, i, new_label)
        self._install_pe_push(path, src_ip, dst_ip, new_label)

    def _install_pe_push(
        self, path: List[int], src_ip: str, dst_ip: str, label: int
    ) -> None:
        dpid = path[0]
        dp = self.datapaths[dpid]
        ofproto = dp.ofproto
        parser = dp.ofproto_parser
        match = parser.OFPMatch(eth_type=ETH_TYPE_IP, ipv4_src=src_ip, ipv4_dst=dst_ip)
        actions = [
            parser.OFPActionPushMpls(),
            parser.OFPActionSetField(mpls_label=label),
            parser.OFPActionOutput(self.neigh[dpid][path[1]]),
        ]
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        self._add_flow(
            dp=dp, table_id=1, priority=PRIO_MPLS, match=match, instructions=inst
        )

    def _install_p_forward(self, path: List[int], i: int, label: int) -> None:
        dpid = path[i]
        dp = self.datapaths[dpid]
        ofproto = dp.ofproto
        parser = dp.ofproto_parser
        match = parser.OFPMatch(eth_type=ETH_TYPE_MPLS, mpls_label=label)
        actions = [parser.OFPActionOutput(self.neigh[dpid][path[i + 1]])]
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        self._add_flow(
            dp=dp, table_id=0, priority=PRIO_MPLS, match=match, instructions=inst
        )

    def _install_pe_pop(self, dpid: int, host_port: int) -> None:
        dp = self.datapaths[dpid]
        ofproto = dp.ofproto
        parser = dp.ofproto_parser
        match = parser.OFPMatch(eth_type=ETH_TYPE_MPLS)
        actions = [
            parser.OFPActionPopMpls(ETH_TYPE_IP),
            parser.OFPActionOutput(host_port),
        ]
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        self._add_flow(
            dp=dp, table_id=0, priority=PRIO_POP, match=match, instructions=inst
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

    def _expire_old_label(
        self, old_label: int, old_path: List[int], stitch_idx: int
    ) -> None:
        end_idx = stitch_idx if stitch_idx is not None else len(old_path) - 1

        for i in range(end_idx - 1, 0, -1):
            dpid = old_path[i]
            if dpid not in self.datapaths:
                continue

            dp = self.datapaths[dpid]
            ofproto = dp.ofproto
            parser = dp.ofproto_parser

            match = parser.OFPMatch(eth_type=ETH_TYPE_MPLS, mpls_label=old_label)
            out_port = self.neigh[dpid][old_path[i + 1]]
            actions = [parser.OFPActionOutput(out_port)]
            inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]

            self._add_flow(
                dp=dp,
                table_id=0,
                priority=PRIO_MPLS,
                match=match,
                instructions=inst,
                idle_timeout=3,
            )
