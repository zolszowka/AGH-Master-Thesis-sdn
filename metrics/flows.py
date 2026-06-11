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

            flows = []
            durations = []

            for line in result.stdout.splitlines():
                if "table=" in line:
                    flows.append(line)

                    if "duration=" in line:
                        try:
                            d = float(line.split("duration=")[1].split("s")[0])
                            durations.append(d)
                        except:
                            pass

            data[sw.name] = {
                "flow_count": len(flows),
                "avg_duration": sum(durations)/len(durations) if durations else 0,
                "max_duration": max(durations) if durations else 0
            }

        return data

    def compute_stats(self, flow_entries):
        sum_pe = 0
        p_vals = []

        for sw in self.pe_switches:
            if sw in flow_entries:
                sum_pe += flow_entries[sw]["flow_count"]

        for sw in self.p_switches:
            if sw in flow_entries:
                p_vals.append(flow_entries[sw]["flow_count"])

        avg_p = sum(p_vals) / len(p_vals) if p_vals else 0
        max_p = max(p_vals) if p_vals else 0

        return {
            "sum_pe": sum_pe,
            "avg_p": avg_p,
            "max_p": max_p
        }
