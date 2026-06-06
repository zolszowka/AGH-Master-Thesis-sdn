import pandas as pd
import numpy as np
import glob
import os
from scipy import stats
import matplotlib.pyplot as plt



# =========================
# 1. foldery danych
# =========================
folders = {
    "basic": "mpls_basic",
    "cached": "mpls_cached",
    "single_path": "single_path",
}

all_dfs = []

# =========================
# 2. wczytanie danych z folderów
# =========================
for label, folder in folders.items():
    files = glob.glob(os.path.join(folder, "flows_*.csv"))

    for file in files:
        df = pd.read_csv(file)

        df["time"] = pd.to_numeric(df["time"], errors="coerce")
        df["sum_flow_entries_PE"] = pd.to_numeric(df["sum_flow_entries_PE"], errors="coerce")
        df["avg_flow_entries_P"] = pd.to_numeric(df["avg_flow_entries_P"], errors="coerce")

        df["scenario"] = label  # <<< kluczowa zmiana
        all_dfs.append(df)

all_data = pd.concat(all_dfs, ignore_index=True)

# =========================
# 3. CI (t-Student)
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
# 4. agregacja po time + scenariusz
# =========================
results = []

for (scenario, time), group in all_data.groupby(["scenario", "time"]):
    for col in ["sum_flow_entries_PE", "avg_flow_entries_P"]:
        mean, std, ci = mean_std_ci(group, col)

        results.append({
            "scenario": scenario,
            "time": time,
            "metric": col,
            "mean": mean,
            "ci_low": ci[0],
            "ci_high": ci[1]
        })

res_df = pd.DataFrame(results)

# =========================
# 5. wykres (NAŁOŻONE DWIE SERIE)
# =========================
def plot_metric(metric_name, ylabel):
    df = res_df[res_df["metric"] == metric_name].sort_values("time")

    fig, ax = plt.subplots()

    scenarios = {
        "basic": ("-", "Podstawowy"),
        "cached": ("-", "Rozszerzony"),
        "single_path": ("-", "Single Path")
    }

    for scenario, (style, label_name) in scenarios.items():
        d = df[df["scenario"] == scenario]

        # asymetryczne błędy (CI)
        yerr = [
            d["mean"] - d["ci_low"],
            d["ci_high"] - d["mean"]
        ]

        ax.errorbar(
            d["time"],
            d["mean"],
            yerr=yerr,
            fmt=style + "o",   # linia + punkty
            linewidth=1,
            markersize=2,
            capsize=1,
            label=label_name
        )

    ax.set_xlabel("Czas [s]")
    ax.set_ylabel(ylabel)

    # clean style
    ax.grid(False)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    ax.set_facecolor("white")
    fig.patch.set_facecolor("white")

    ax.legend()

    filename = f"{metric_name}_comparison.png"
    plt.savefig(filename, dpi=300, bbox_inches="tight")
    plt.close()

    print(f"Saved: {filename}")
# =========================
# 6. wykresy końcowe
# =========================
plot_metric("sum_flow_entries_PE", "Suma wpisów w tablicach DFT w węzłach PE")
plot_metric("avg_flow_entries_P", "Średnia liczba wpisów\nw tablicach przepływów w węzłach P")