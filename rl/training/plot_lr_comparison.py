from pathlib import Path
import matplotlib.pyplot as plt
import json


COLORS = ["#e74c3c", "#3498db", "#2ecc71"]


def load_json(json_file):
    with open(json_file, "r") as f:
        data = json.load(f)
    steps = [point[0] for point in data]
    rewards = [point[1] for point in data]
    return steps, rewards


def plot_individual(rewards_dir: Path, out_dir: Path):
    for i, json_file in enumerate(sorted(rewards_dir.glob("rewards_lr_*.json"))):
        lr = float(json_file.stem.replace("rewards_lr_", ""))
        steps, rewards = load_json(json_file)
        if not steps:
            continue

        fig, ax = plt.subplots(figsize=(12, 6))
        ax.plot(steps, rewards, alpha=0.8, linewidth=0.9, color=COLORS[i % len(COLORS)])
        ax.set_xlabel("Step", fontsize=12)
        ax.set_ylabel("Reward", fontsize=12)
        ax.set_title(f"Reward par step — lr = {lr}", fontsize=13)
        ax.set_xlim(left=0)
        ax.grid(True, alpha=0.3)
        fig.tight_layout()

        save_path = out_dir / f"step_reward_lr_{lr}.png"
        fig.savefig(save_path, dpi=200)
        plt.close()
        print(f"Sauvegardé : {save_path}")


def plot_comparison(rewards_dir: Path, out_dir: Path):
    fig, ax = plt.subplots(figsize=(12, 6))
    found_any = False

    for i, json_file in enumerate(sorted(rewards_dir.glob("rewards_lr_*.json"))):
        lr = float(json_file.stem.replace("rewards_lr_", ""))
        steps, rewards = load_json(json_file)
        if not steps:
            continue

        ax.plot(steps, rewards, alpha=0.7, linewidth=0.8,
                color=COLORS[i % len(COLORS)], label=f"lr = {lr}")
        print(f"  lr={lr} : {len(steps)} steps chargés")
        found_any = True

    if not found_any:
        print("Aucune donnée trouvée.")
        plt.close()
        return

    ax.set_xlabel("Step", fontsize=12)
    ax.set_ylabel("Reward", fontsize=12)
    ax.set_title("Reward par step — comparaison des learning rates", fontsize=13)
    ax.set_xlim(left=0)
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=11)
    fig.tight_layout()

    save_path = out_dir / "step_reward_per_lr.png"
    fig.savefig(save_path, dpi=200)
    plt.close()
    print(f"Sauvegardé : {save_path}")


def main():
    root = Path(__file__).resolve().parents[2]
    rewards_dir = Path("rewards_data_lr")
    out_dir = root / "compare_lr_plots"
    out_dir.mkdir(exist_ok=True)

    plot_individual(rewards_dir, out_dir)
    plot_comparison(rewards_dir, out_dir)
    print(f"\nTous les graphes dans : {out_dir}")


if __name__ == "__main__":
    main()
