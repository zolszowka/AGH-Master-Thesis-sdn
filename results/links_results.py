import re
import glob
import os
import csv
import numpy as np
from collections import defaultdict
from scipy import stats
import pandas as pd


# =========================
# Parse logs
# =========================
def parse_runs(logs_dir):
    all_samples = defaultdict(list)
    run_peaks = defaultdict(list)

    pattern = re.compile(r"dpid=(\d+)\s+port=(\d+)\s+throughput=([\d.]+)")

    log_files = sorted(glob.glob(os.path.join(logs_dir, "*.log")))

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


# =========================
# Mean, standard deviation and confidence interval
# =========================
def mean_std_ci(data, confidence=0.95):
    data = pd.Series(data).dropna()
    n = len(data)

    mean = data.mean()
    std = data.std(ddof=1)

    if n < 2:
        return mean, std, (np.nan, np.nan)

    se = std / np.sqrt(n)
    t_crit = stats.t.ppf((1 + confidence) / 2, df=n - 1)

    ci = (mean - t_crit * se, mean + t_crit * se)

    return mean, std, ci


# =========================
# Analyze single scenario
# =========================
def analyze_logs(logs_dir):
    all_samples, run_peaks = parse_runs(logs_dir)

    results = []

    for key in sorted(all_samples):
        dpid, port = key

        samples = all_samples[key]
        peaks = run_peaks[key]

        avg, std, (avg_low, avg_high) = mean_std_ci(samples)
        peak_mean, std, (peak_low, peak_high) = mean_std_ci(peaks)

        results.append(
            [
                dpid,
                port,
                round(avg, 2),
                round((avg_high - avg_low) / 2, 2),
                round(peak_mean, 2),
                round((peak_high - peak_low) / 2, 2),
            ]
        )

    return results


# =========================
# Save CSV
# =========================
base_dir = os.path.dirname(os.path.abspath(__file__))

scenarios = {
    "mpls_basic": os.path.join(base_dir, "mpls_basic/logs"),
    "mpls_cached": os.path.join(base_dir, "mpls_cached/logs"),
    "single_path": os.path.join(base_dir, "single_path/logs"),
}

output_file = os.path.join(base_dir, "links_results.csv")

with open(output_file, "w", newline="") as f:
    writer = csv.writer(f)

    writer.writerow(
        [
            "scenario",
            "dpid",
            "port",
            "avg_mbps",
            "ci95_avg",
            "avg_peak",
            "ci95_peak",
        ]
    )

    for scenario, path in scenarios.items():

        if not os.path.exists(path):
            print(f"[WARN] missing: {path}")
            continue

        results = analyze_logs(path)

        for row in results:
            writer.writerow([scenario] + row)

print(f"Saved: links_results.csv")
