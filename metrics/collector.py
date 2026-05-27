import csv
import time

from metrics.throughput import ThroughputMonitor
from metrics.flows import FlowMonitor
from metrics.control_plane import ControlPlaneMonitor


class MetricsCollector:
    def __init__(self, net, hosts, pe_switches, p_switches):
        self.net = net
        self.hosts = hosts

        self.throughput = ThroughputMonitor()

        self.flows = FlowMonitor(net, pe_switches, p_switches)

        self.control_plane = ControlPlaneMonitor(pe_switches, p_switches)

    def collect_all(
        self, throughput_csv, flow_csv, control_csv, duration=60, interval=1
    ):

        self.control_plane.start()

        with open(throughput_csv, "w", newline="") as tfile, open(
            flow_csv, "w", newline=""
        ) as ffile:

            t_writer = csv.writer(tfile)
            f_writer = csv.writer(ffile)

            t_writer.writerow(
                ["time", "tx_bytes", "rx_bytes", "loss_percent", "throughput_bps"]
            )

            f_writer.writerow(
                [
                    "time",
                    "sum_flow_entries_PE",
                    "avg_flow_entries_P",
                    "max_flow_entries_P",
                ]
            )

            _, rx_start = self.throughput.get_total_bytes(self.hosts)

            for t in range(duration + 1):
                loop_start = time.time()

                tx_total, rx_total = self.throughput.get_total_bytes(self.hosts)

                loss = self.throughput.compute_loss(tx_total, rx_total)

                throughput = self.throughput.compute_throughput(
                    rx_start, rx_total, t + 1
                )

                t_writer.writerow([t, tx_total, rx_total, loss, throughput])

                flow_entries = self.flows.get_flow_entries()
                flow_stats = self.flows.compute_stats(flow_entries)

                f_writer.writerow(
                    [t, flow_stats["sum_pe"], flow_stats["avg_p"], flow_stats["max_p"]]
                )

                elapsed = time.time() - loop_start

                if elapsed < interval:
                    time.sleep(interval - elapsed)

        self.control_plane.stop()

        control_stats = self.control_plane.parse_logs()
        self.export_control_plane_csv(control_csv, control_stats)

    def collect_throughput_only(self, output_csv, duration=60, interval=1):
        pass

    def collect_flows_only(self, output_csv, duration=60, interval=1):
        pass

    def collect_control_plane_only(self, output_csv, duration=60):

        self.control_plane.start()

        time.sleep(duration)

        self.control_plane.stop()

        stats = self.control_plane.parse_logs()

        self.export_control_plane_csv(output_csv, stats)

    def export_control_plane_csv(self, filename, stats):
        with open(filename, "w", newline="") as f:
            writer = csv.writer(f)

            writer.writerow(["switch", "flow_mod", "packet_in"])

            for sw, data in stats["per_switch"].items():
                writer.writerow([sw, data["flow_mod"], data["packet_in"]])

            writer.writerow(
                [
                    "TOTAL_P_SWITCHES",
                    stats["p_switches"]["flow_mod"],
                    stats["p_switches"]["packet_in"],
                ]
            )

            writer.writerow(
                [
                    "TOTAL_PE_SWITCHES",
                    stats["pe_switches"]["flow_mod"],
                    stats["pe_switches"]["packet_in"],
                ]
            )

            writer.writerow(
                [
                    "TOTAL_ALL_SWITCHES",
                    stats["total"]["flow_mod"],
                    stats["total"]["packet_in"],
                ]
            )
