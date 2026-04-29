import config as c
import glob
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path
cfg= c.PPOConfig()
logs_dir =cfg.logs_dir

# Charger et fusionner tous les fichiers
dfs = []
for f in glob.glob(f"{logs_dir}/rewards_env_*.csv"):
    df = pd.read_csv(f, names=["episode", "reward", "timestamp"])
    dfs.append(df)

if not dfs:
    print("Aucun fichier de rewards trouvé.")
else:
    df = pd.concat(dfs).sort_values("timestamp").reset_index(drop=True)
    df["episode"] = range(len(df))  # renumérotation globale chronologique

    plt.figure(figsize=(12, 5))
    plt.plot(df["episode"], df["reward"], alpha=0.3, color="steelblue", label="reward brute")
    plt.plot(df["episode"], df["reward"].rolling(500).mean(), color="red", linewidth=2, label="moyenne mobile 500")
    plt.xlabel("Épisode")
    plt.ylabel("Reward")
    plt.title("Reward par épisode")
    plt.legend()
    plt.tight_layout()
    plt.savefig(f"{logs_dir}/reward_curve.png")
    plt.show()
    print(f"Courbe sauvegardée dans {logs_dir}/reward_curve.png")