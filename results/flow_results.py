import pandas as pd
import numpy as np
import glob
import os
from scipy import stats
import matplotlib.pyplot as plt

# =========================
# 1. Data folders
# =========================
folders = {
    "basic": "mpls_basic",
    "cached": "mpls_cached",
    "single_path": "single_path",
}

all_dfs = []

# =========================
# 2. Load data from folders
# =========================
for label, folder in folders.items():
    files = glob.glob(os.path.join(folder, "flows_*.csv"))

    for file in files:
        df = pd.read_csv(file)

        df["time"] = pd.to_numeric(df["time"], errors="coerce")
        df["sum_flow_entries_PE"] = pd.to_numeric(
            df["sum_flow_entries_PE"], errors="coerce"
        )
        df["avg_flow_entries_P"] = pd.to_numeric(
            df["avg_flow_entries_P"], errors="coerce"
        )

        # Add scenario label
        df["scenario"] = label
        all_dfs.append(df)

all_data = pd.concat(all_dfs, ignore_index=True)

# =========================
# 3. Mean, standard deviation and confidence interval
# =========================
def mean_std_ci(group, column, confidence=0.95):
    data = group[column].dropna()
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
# 4. Aggregate results by scenario and time
# =========================
results = []

for (scenario, time), group in all_data.groupby(["scenario", "time"]):
    for col in ["sum_flow_entries_PE", "avg_flow_entries_P"]:

        mean, std, (ci_low, ci_high) = mean_std_ci(group, col)

        results.append(
            {
                "scenario": scenario,
                "time": time,
                "metric": col,
                "mean": mean,
                "ci_low": ci_low,
                "ci_high": ci_high,
            }
        )

res_df = pd.DataFrame(results)

# =========================
# 5. Plot
# =========================
def plot_metric(metric_name, ylabel, scenarios_to_plot, filename_suffix):

    df = res_df[res_df["metric"] == metric_name].sort_values("time")

    fig, ax = plt.subplots()

    scenario_info = {
        "basic": ("-", "Wariant I"),
        "cached": ("-", "Wariant II"),
        "single_path": ("-", "Single Path"),
    }

    for scenario in scenarios_to_plot:

        style, label_name = scenario_info[scenario]

        d = df[df["scenario"] == scenario]

        if d.empty:
            print(f"No data for {scenario}")
            continue

        yerr = [d["mean"] - d["ci_low"], d["ci_high"] - d["mean"]]

        ax.errorbar(
            d["time"],
            d["mean"],
            yerr=yerr,
            fmt=style + "o",
            linewidth=1,
            markersize=2,
            capsize=2,
            label=label_name,
        )

    ax.set_xlabel("Czas [s]")
    ax.set_ylabel(ylabel)
    ax.set_xlim(left=0)
    ax.grid(False)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.set_facecolor("white")
    fig.patch.set_facecolor("white")

    ax.legend()

    filename = f"{metric_name}_{filename_suffix}.png"

    plt.savefig(filename, dpi=300, bbox_inches="tight")

    plt.close()

    print(f"Saved: {filename}")


# =========================
# 6. Generate plots
# =========================
metrics = [
    ("sum_flow_entries_PE", "Suma wpisów w tablicach DFT w węzłach PE"),
    ("avg_flow_entries_P", "Średnia liczba wpisów\nw tablicach przepływów w węzłach P"),
]

plot_configs = [
    (["basic"], "basic"),
    (["cached"], "cached"),
    (["single_path"], "single_path"),
    (["basic", "cached"], "basic_vs_cached"),
    (["basic", "cached", "single_path"], "all"),
]

for metric, ylabel in metrics:
    for scenarios, suffix in plot_configs:
        plot_metric(metric, ylabel, scenarios, suffix)
