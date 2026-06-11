import os
import time
import subprocess


class ControlPlaneMonitor:
    def __init__(self, pe_switches, p_switches, log_dir="snoop_logs"):
        self.pe_switches = pe_switches
        self.p_switches = p_switches
        self.log_dir = log_dir

        self.processes = {}
        self.log_files = {}

        os.makedirs(log_dir, exist_ok=True)

    def start(self):
        for sw in self.p_switches:
            log_path = os.path.join(self.log_dir, f"{sw}.log")

            log_file = open(log_path, "w")
            self.log_files[sw] = log_file

            proc = subprocess.Popen(
                ["sudo", "ovs-ofctl", "snoop", sw],
                stdout=log_file,
                stderr=subprocess.STDOUT,
                text=True,
            )

            self.processes[sw] = proc

        time.sleep(1)

    def stop(self):
        for proc in self.processes.values():
            proc.terminate()

            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()

        for f in self.log_files.values():
            f.close()

    def parse_logs(self):
        stats = {}

        total_flow_mod = 0
        total_packet_in = 0
        total_packet_out = 0

        total_p_flow_mod = 0
        total_p_packet_in = 0
        total_p_packet_out = 0

        total_pe_flow_mod = 0
        total_pe_packet_in = 0
        total_pe_packet_out = 0

        for sw in self.p_switches:
            flow_mod = 0
            packet_in = 0
            packet_out = 0

            try:
                with open(f"{self.log_dir}/{sw}.log") as f:
                    lines = f.readlines()

                for i, line in enumerate(lines):
                    if "OFPT_FLOW_MOD" in line:
                        flow_mod += 1
                    elif "OFPT_PACKET_IN" in line and (i + 1 < len(lines) and lines[i + 1].startswith("udp,")):
                        packet_in += 1
                    elif "OFPT_PACKET_OUT" in line and (i + 1 < len(lines) and lines[i + 1].startswith("udp,")):
                        packet_out += 1

            except FileNotFoundError:
                pass

            stats[sw] = {"flow_mod": flow_mod, "packet_in": packet_in, "packet_out": packet_out}

            total_flow_mod += flow_mod
            total_packet_in += packet_in
            total_packet_out += packet_out

            if sw in self.p_switches:
                total_p_flow_mod += flow_mod
                total_p_packet_in += packet_in
                total_p_packet_out += packet_out

            if sw in self.pe_switches:
                total_pe_flow_mod += flow_mod
                total_pe_packet_in += packet_in
                total_pe_packet_out += packet_out

        return {
            "per_switch": stats,
            "total": {"flow_mod": total_flow_mod, "packet_in": total_packet_in, "packet_out": total_packet_out},
            "p_switches": {
                "flow_mod": total_p_flow_mod,
                "packet_in": total_p_packet_in,
                "packet_out": total_p_packet_out,
            },
            "pe_switches": {
                "flow_mod": total_pe_flow_mod,
                "packet_in": total_pe_packet_in,
                "packet_out": total_p_packet_out,
            },
        }
