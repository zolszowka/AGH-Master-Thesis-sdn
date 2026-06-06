import re
import glob
import os
import csv
import numpy as np
from collections import defaultdict
from scipy import stats


class LinksMonitor:
    def __init__(self, logs_dir):
        self.logs_dir = logs_dir

    def parse_runs(self):
        all_samples = defaultdict(list)
        run_peaks = defaultdict(list)

        pattern = re.compile(r"dpid=(\d+)\s+port=(\d+)\s+throughput=([\d.]+)")

        log_files = sorted(glob.glob(os.path.join(self.logs_dir, "*.log")))

        for path in log_files:
            run_samples = defaultdict(list)

            with open(path) as f:
                for line in f:
                    m = pattern.search(line)
                    if not m:
                        continue

                    key = (int(m.group(1)), int(m.group(2)))
                    run_samples[key].append(float(m.group(3)))

            for key, values in run_samples.items():
                all_samples[key].extend(values)
                run_peaks[key].append(max(values))

        return all_samples, run_peaks

    def ci95(self, data):
        n = len(data)
        if n < 2:
            return np.mean(data), 0.0

        mean = np.mean(data)
        std = np.std(data, ddof=1)

        t_val = stats.t.ppf(0.975, df=n - 1)
        margin = t_val * std / np.sqrt(n)

        return mean, margin

    def analyze(self):
        all_samples, run_peaks = self.parse_runs()

        results = []

        for key in sorted(all_samples):
            dpid, port = key

            samples = all_samples[key]
            peaks = run_peaks[key]

            avg, ci = self.ci95(samples)

            results.append([
                dpid,
                port,
                round(avg, 4),
                round(ci, 4),
                round(np.mean(peaks), 4),
                round(np.std(peaks, ddof=1), 4),
            ])

        return results


def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))

    scenarios = {
        "mpls_basic": os.path.join(base_dir, "mpls_basic/logs"),
        "mpls_cached": os.path.join(base_dir, "mpls_cached/logs"),
        "single_path": os.path.join(base_dir, "single_path/logs"),
    }

    output_file = os.path.join(base_dir, "links_results.csv")

    with open(output_file, "w", newline="") as f:
        writer = csv.writer(f)

        writer.writerow([
            "scenario",
            "dpid",
            "port",
            "avg_mbps",
            "ci95_mbps",
            "avg_peak",
            "std_peak"
        ])

        for scenario, path in scenarios.items():
            if not os.path.exists(path):
                print(f"[WARN] missing: {path}")
                continue

            monitor = LinksMonitor(path)
            results = monitor.analyze()

            for row in results:
                writer.writerow([scenario] + row)

    print(f"[OK] saved: {output_file}")


if __name__ == "__main__":
    main()