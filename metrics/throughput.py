import re

class ThroughputMonitor:
    def __init__(self):
        self.prev_tx_packets = None
        self.prev_rx_packets = None

        self.prev_tx_bytes = None
        self.prev_rx_bytes = None

    def get_host_stats(self, host):
        out = host.cmd("cat /proc/net/dev")
        match = re.search(r"eth0:\s*([\d\s]+)", out)
        if match:
            parts = match.group(1).split()

            rx_bytes = int(parts[0])
            rx_packets = int(parts[1])
            rx_errs = int(parts[2])
            rx_drop = int(parts[3])

            tx_bytes = int(parts[8])
            tx_packets = int(parts[9])
            tx_errs = int(parts[10])
            tx_drop = int(parts[11])

            return {
                "tx_bytes": tx_bytes,
                "rx_bytes": rx_bytes,
                "tx_packets": tx_packets,
                "rx_packets": rx_packets,
                "tx_errs": tx_errs,
                "rx_errs": rx_errs,
                "tx_drop": tx_drop,
                "rx_drop": rx_drop,
            }

        return {
            "tx_bytes": 0,
            "rx_bytes": 0,
            "tx_packets": 0,
            "rx_packets": 0,
            "tx_errs": 0,
            "rx_errs": 0,
            "tx_drop": 0,
            "rx_drop": 0,
        }

    def get_total_stats(self, hosts):
        agg = {
            "tx_bytes": 0,
            "rx_bytes": 0,
            "tx_packets": 0,
            "rx_packets": 0,
            "tx_errs": 0,
            "rx_errs": 0,
            "tx_drop": 0,
            "rx_drop": 0,
        }

        for host in hosts:
            s = self.get_host_stats(host)
            for k in agg:
                agg[k] += s[k]

        return agg

    def compute_loss_total(self, tx_packets, rx_packets):
        if tx_packets <= 0:
            return 0.0

        lost = tx_packets - rx_packets
        if lost < 0:
            lost = 0

        return (lost / tx_packets) * 100.0     
           
    def compute_loss(self, tx_packets, rx_packets):
        if self.prev_tx_packets is None:
            self.prev_tx_packets = tx_packets
            self.prev_rx_packets = rx_packets
            return 0.0

        tx_diff = tx_packets - self.prev_tx_packets
        rx_diff = rx_packets - self.prev_rx_packets

        self.prev_tx_packets = tx_packets
        self.prev_rx_packets = rx_packets

        if tx_diff <= 0:
            return 0.0

        lost = tx_diff - rx_diff
        return max((lost / tx_diff) * 100.0, 0.0)

    def compute_throughput(self, rx_now_bytes, rx_start_bytes, elapsed_seconds):
        if elapsed_seconds <= 0:
            return 0.0

        return ((rx_now_bytes - rx_start_bytes) * 8) / elapsed_seconds