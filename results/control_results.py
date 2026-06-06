import pandas as pd
import numpy as np
import glob
import os
from scipy import stats
import matplotlib.pyplot as plt

# =========================
# folders
# =========================
folders = {
    "mpls_basic": "Podstawowy",
    "mpls_cached": "Rozszerzony",
    "single_path": "Single_Path",
}

TARGET_METRIC = "TOTAL_ALL_SWITCHES"

all_rows = []

# =========================
# LOAD
# =========================
for folder, scenario_name in folders.items():

    files = glob.glob(os.path.join(folder, "control_*.csv"))

    for file in files:

        df = pd.read_csv(file)
        df.columns = df.columns.str.strip()

        # tylko TOTAL_ALL_SWITCHES
        df = df[df["switch"] == TARGET_METRIC]

        if df.empty:
            continue

        for _, row in df.iterrows():
            all_rows.append({
                "scenario": scenario_name,
                "value": row["flow_mod"],
                "packet_in": row["packet_in"]
            })

all_data = pd.DataFrame(all_rows)

if all_data.empty:
    raise ValueError("Brak danych!")

# =========================
# CI
# =========================
def mean_std_ci(x):
    x = pd.Series(x).dropna()
    n = len(x)

    mean = x.mean()
    std = x.std(ddof=1)

    if n < 2:
        return mean, std, (np.nan, np.nan)

    se = std / np.sqrt(n)
    t = stats.t.ppf(0.975, df=n - 1)

    return mean, std, (mean - t * se, mean + t * se)

# =========================
# TABLE
# =========================
rows = []

for scenario in folders.values():

    subset = all_data[all_data["scenario"] == scenario]

    mean, std, (low, high) = mean_std_ci(subset["value"])

    packet_mean = subset["packet_in"].mean()

    rows.append({
        "Scenariusz": scenario,
        "FLOW_MOD": f"{mean:.1f} ± {(high - mean):.1f}",
        "PACKET_IN": f"{packet_mean:.1f}"
    })

table_df = pd.DataFrame(rows)

# =========================
# SAVE CSV
# =========================
table_df.to_csv("control_all_switches.csv", index=False)

# =========================
# SAVE PNG
# =========================
fig, ax = plt.subplots(figsize=(8, 2.5))
ax.axis("off")

ax.set_title(
    "Liczba komunikatów FLOW_MOD i PACKET_IN",
    fontsize=14,
    fontweight="bold",
    pad=20
)

table = ax.table(
    cellText=table_df.values,
    colLabels=table_df.columns,
    cellLoc="center",
    loc="center"
)

table.auto_set_font_size(False)
table.set_fontsize(11)
table.scale(1.2, 1.5)

plt.savefig("control_all_switches.png", dpi=300, bbox_inches="tight")
plt.close()

print(table_df)

print("\nSaved:")
print("- control_all_switches.csv")
print("- control_all_switches.png")