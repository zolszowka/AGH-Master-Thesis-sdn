import subprocess


class FlowMonitor:
    def __init__(self, net, pe_switches, p_switches):
        self.net = net
        self.pe_switches = pe_switches
        self.p_switches = p_switches

    def get_flow_entries(self):
        data = {}

        for sw in self.net.switches:
            result = subprocess.run(
                ["sudo", "ovs-ofctl", "dump-flows", sw.name],
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                data[sw.name] = 0
                continue

            count = sum(1 for line in result.stdout.splitlines() if "table=" in line)

            data[sw.name] = count

        return data

    def compute_stats(self, flow_entries):
        sum_pe = sum(flow_entries.get(sw, 0) for sw in self.pe_switches)

        p_values = [flow_entries.get(sw, 0) for sw in self.p_switches]

        avg_p = sum(p_values) / len(p_values) if p_values else 0
        max_p = max(p_values) if p_values else 0

        return {"sum_pe": sum_pe, "avg_p": avg_p, "max_p": max_p}
