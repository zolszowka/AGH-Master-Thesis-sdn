class ThroughputMonitor:
    def __init__(self):
        self.prev_tx = None
        self.prev_rx = None

    def get_host_bytes(self, host):
        out = host.cmd("cat /proc/net/dev")

        for line in out.splitlines():
            if "eth0" in line:
                parts = line.split()
                rx_bytes = int(parts[1])
                tx_bytes = int(parts[9])
                return tx_bytes, rx_bytes

        return 0, 0

    def get_total_bytes(self, hosts):
        tx_total = 0
        rx_total = 0

        for host in hosts:
            tx, rx = self.get_host_bytes(host)
            tx_total += tx
            rx_total += rx

        return tx_total, rx_total

    def compute_loss(self, tx, rx):
        if self.prev_tx is None:
            self.prev_tx = tx
            self.prev_rx = rx
            return 0

        tx_diff = tx - self.prev_tx
        rx_diff = rx - self.prev_rx

        self.prev_tx = tx
        self.prev_rx = rx

        if tx_diff <= 0:
            return 0

        return max((tx_diff - rx_diff) / tx_diff * 100, 0)

    def compute_throughput(self, rx_start, rx_now, elapsed):
        if elapsed <= 0:
            return 0

        return (rx_now - rx_start) * 8 / elapsed
