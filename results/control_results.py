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

TARGET_METRIC = "TOTAL"

all_rows = []

# =========================
# 2. Load data from folders
# =========================
for label, folder in folders.items():

    files = glob.glob(os.path.join(folder, "control_*.csv"))
    for file in files:
        df = pd.read_csv(file)
        df.columns = df.columns.str.strip()

        # tylko TOTAL_ALL_SWITCHES
        df = df[df["switch"] == TARGET_METRIC]

        if df.empty:
            continue

        for _, row in df.iterrows():
            all_rows.append(
                {
                    "scenario": label,
                    "flow_mod": row["flow_mod"],
                    "packet_in": row["packet_in"],
                    "packet_out": row["packet_out"],
                }
            )

all_data = pd.DataFrame(all_rows)

if all_data.empty:
    raise ValueError("No data loaded")

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
# 4. Table
# =========================
scenarios = {"basic": "Wariant I", "cached": "Wariant II", "single_path": "Single Path"}

rows = []

for scenario in scenarios.keys():

    subset = all_data[all_data["scenario"] == scenario]

    # FLOW_MOD
    flow_mean, flow_std, (flow_low, flow_high) = mean_std_ci(subset, "flow_mod")

    # PACKET_IN
    pin_mean, pin_std, (pin_low, pin_high) = mean_std_ci(subset, "packet_in")

    # PACKET_OUT
    pout_mean, pout_std, (pout_low, pout_high) = mean_std_ci(subset, "packet_out")

    rows.append(
        {
            "Algorytm": scenario,
            "FLOW_MOD": f"{flow_mean:.2f} ± {(flow_high - flow_low)/2:.2f}",
            "PACKET_IN": f"{pin_mean:.2f} ± {(pin_high - pin_low)/2:.2f}",
            "PACKET_OUT": f"{pout_mean:.2f} ± {(pout_high - pout_low)/2:.2f}",
        }
    )

table_df = pd.DataFrame(rows)

# =========================
# 5. Save CSV
# =========================
table_df.to_csv("control_all_switches.csv", index=False)

# =========================
# 6. Save PNG
# =========================
fig, ax = plt.subplots(figsize=(8, 2.5))
ax.axis("off")

table = ax.table(
    cellText=table_df.values, colLabels=table_df.columns, cellLoc="center", loc="center"
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
