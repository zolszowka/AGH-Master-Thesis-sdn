import csv
import time

from metrics.throughput import ThroughputMonitor
from metrics.flows import FlowMonitor
from metrics.control_plane import ControlPlaneMonitor
from metrics.cpu import CPUMonitor


class MetricsCollector:
    def __init__(self, net, hosts, pe_switches, p_switches, log_dir="snoop_logs"):
        self.net = net
        self.hosts = hosts
        self.log_dir = log_dir

        self.throughput = ThroughputMonitor()
        self.flows = FlowMonitor(net, pe_switches, p_switches)
        self.control_plane = ControlPlaneMonitor(pe_switches, p_switches, self.log_dir)
        self.cpu_monitor = CPUMonitor()

    def collect_all(
        self, throughput_csv, flow_csv, control_csv, cpu_csv, duration=60, interval=1
    ):
        self.control_plane.start()

        with open(throughput_csv, "w", newline="") as tfile, \
             open(flow_csv, "w", newline="") as ffile:
            #  open(cpu_csv, "w", newline="") as cfile:

            t_writer = csv.writer(tfile)
            f_writer = csv.writer(ffile)
            # c_writer = csv.writer(cfile)

            t_writer.writerow([
                "time",
                "tx_bytes",
                "rx_bytes",
                "tx_packets",
                "rx_packets",
                "loss_percent",
                "throughput_bps"
            ])

            f_writer.writerow([
                "time",
                "sum_flow_entries_PE",
                "avg_flow_entries_P",
                "max_flow_entries_P",
            ])

            # c_writer.writerow([
            #     "time",
            #     "ryu_cpu_percent",
            #     "ryu_ram_mb"
            # ])

            start_time = time.time()

            start_stats = self.throughput.get_total_stats(self.hosts)
            rx_start_bytes = start_stats["rx_bytes"]

            for t in range(duration + 1):
                loop_start = time.time()

                # ==== Throughput Stats ====
                stats = self.throughput.get_total_stats(self.hosts)

                tx_bytes = stats["tx_bytes"]
                rx_bytes = stats["rx_bytes"]

                tx_packets = stats["tx_packets"]
                rx_packets = stats["rx_packets"]

                loss = self.throughput.compute_loss(tx_packets, rx_packets)

                elapsed_real = time.time() - start_time

                throughput = self.throughput.compute_throughput(
                    rx_bytes, rx_start_bytes, elapsed_real
                )

                t_writer.writerow([
                    t,
                    tx_bytes,
                    rx_bytes,
                    tx_packets,
                    rx_packets,
                    loss,
                    throughput
                ])

                # ==== Flow Tables Stats ====
                flow_entries = self.flows.get_flow_entries()
                flow_stats = self.flows.compute_stats(flow_entries)

                f_writer.writerow([
                    t,
                    flow_stats["sum_pe"],
                    flow_stats["avg_p"],
                    flow_stats["max_p"]
                ])

                # ==== CPU and RAM Stats ====
                # cpu_stats = self.cpu_monitor.get_stats()
                # c_writer.writerow([
                #     t,
                #     cpu_stats["ryu_cpu_percent"],
                #     cpu_stats["ryu_ram_mb"]
                # ])

                elapsed_loop = time.time() - loop_start

                if elapsed_loop < interval:
                    time.sleep(interval - elapsed_loop)

        self.control_plane.stop()

        control_stats = self.control_plane.parse_logs()
        self.export_control_plane_csv(control_csv, control_stats)

    def collect_throughput_only(self, output_csv, duration=60, interval=1):
        start_time = time.time()
        start_stats = self.throughput.get_total_stats(self.hosts)
        rx_start_bytes = start_stats["rx_bytes"]

        with open(output_csv, "w", newline="") as f:
            writer = csv.writer(f)

            writer.writerow([
                "time",
                "tx_bytes",
                "rx_bytes",
                "tx_packets",
                "rx_packets",
                "loss_percent",
                "throughput_bps"
            ])

            for t in range(duration + 1):
                loop_start = time.time()

                stats = self.throughput.get_total_stats(self.hosts)

                loss = self.throughput.compute_loss(
                    stats["tx_packets"],
                    stats["rx_packets"]
                )

                elapsed_real = time.time() - start_time

                throughput = self.throughput.compute_throughput(
                    stats["rx_bytes"],
                    rx_start_bytes,
                    elapsed_real
                )

                writer.writerow([
                    t,
                    stats["tx_bytes"],
                    stats["rx_bytes"],
                    stats["tx_packets"],
                    stats["rx_packets"],
                    loss,
                    throughput
                ])

                elapsed_loop = time.time() - loop_start
                if elapsed_loop < interval:
                    time.sleep(interval - elapsed_loop)

    def collect_flows_only(self, output_csv, duration=60, interval=1):
        with open(output_csv, "w", newline="") as f:
            writer = csv.writer(f)

            writer.writerow([
                "time",
                "sum_flow_entries_PE",
                "avg_flow_entries_P",
                "max_flow_entries_P",
            ])

            for t in range(duration + 1):
                loop_start = time.time()

                flow_entries = self.flows.get_flow_entries()
                flow_stats = self.flows.compute_stats(flow_entries)

                writer.writerow([
                    t,
                    flow_stats["sum_pe"],
                    flow_stats["avg_p"],
                    flow_stats["max_p"]
                ])

                elapsed = time.time() - loop_start
                if elapsed < interval:
                    time.sleep(interval - elapsed)

    def collect_control_plane_only(self, output_csv, duration=60):
        self.control_plane.start()
        time.sleep(duration)
        self.control_plane.stop()

        stats = self.control_plane.parse_logs()
        self.export_control_plane_csv(output_csv, stats)

    def export_control_plane_csv(self, filename, stats):
        with open(filename, "w", newline="") as f:
            writer = csv.writer(f)

            writer.writerow(["switch", "flow_mod", "packet_in", "packet_out"])

            for sw, data in stats["per_switch"].items():
                writer.writerow([sw, data["flow_mod"], data["packet_in"], data["packet_out"]])

            writer.writerow(
                [
                    "TOTAL",
                    stats["total"]["flow_mod"],
                    stats["total"]["packet_in"],
                    stats["total"]["packet_out"]
                ]
            )
