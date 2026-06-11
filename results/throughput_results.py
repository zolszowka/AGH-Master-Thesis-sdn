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

results = []

# =========================
# 2. Load data from folders
# =========================
for label, folder in folders.items():
    files = glob.glob(os.path.join(folder, "throughput_*.csv"))

    for file in files:
        df = pd.read_csv(file)

        df["scenario"] = label

        tx_total = df["tx_bytes"].iloc[-1] - df["tx_bytes"].iloc[0]
        rx_total = df["rx_bytes"].iloc[-1] - df["rx_bytes"].iloc[0]

        tx_packets_total = df["tx_packets"].iloc[-1] - df["tx_packets"].iloc[0]
        rx_packets_total = df["rx_packets"].iloc[-1] - df["rx_packets"].iloc[0]

        duration = df["time"].iloc[-1] - df["time"].iloc[0]

        loss = 0.0
        if tx_packets_total > 0:
            loss = (tx_packets_total - rx_packets_total) / tx_packets_total * 100

        tput_mbps = 0.0
        if duration > 0:
            tput_mbps = (rx_total * 8) / duration / 1e6

        results.append(
            {
                "scenario": label,
                "tx_gb": tx_total / (1024**3),
                "rx_gb": rx_total / (1024**3),
                "packet_loss": loss,
                "tput_mbps": tput_mbps,
            }
        )

all_data = pd.DataFrame(results)

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

metrics = {
    "tx_gb": "TX [GB]",
    "rx_gb": "RX [GB]",
    "packet_loss": "Strata pakietów [%]",
    "tput_mbps": "Przepustowość [Mb/s]",
}

rows = []

for scenario in scenarios.keys():

    subset = all_data[all_data["scenario"] == scenario]

    row = {"Algorytm": scenarios[scenario]}

    for col, _ in metrics.items():

        mean, std, (low, high) = mean_std_ci(subset, col)

        ci_half = (high - low) / 2

        row[f"{col}"] = f"{mean:.2f} ± {ci_half:.2f}"

    rows.append(row)

table_df = pd.DataFrame(rows)
table_df = table_df.rename(columns=metrics)

# =========================
# 5. Save CSV
# =========================
table_df.to_csv("throughput_results.csv", index=False)

# =========================
# 6. Save PNG
# =========================
fig, ax = plt.subplots(figsize=(10, 2.5))
ax.axis("off")

ax.table(
    cellText=table_df.values, colLabels=table_df.columns, cellLoc="center", loc="center"
)

plt.savefig("throughput_results.png", dpi=300, bbox_inches="tight")
plt.close()

print(table_df)
print("Saved: throughput_results.csv + throughput_results.png")
