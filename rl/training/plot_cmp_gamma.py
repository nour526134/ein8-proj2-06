import re
from pathlib import Path
import matplotlib.pyplot as plt
import pandas as pd
from tensorboard.backend.event_processing.event_accumulator import EventAccumulator


def sanitize_filename(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]", "_", name)


def get_gamma_runs(log_root):
    log_root = Path(log_root)

    if not log_root.exists():
        raise FileNotFoundError(f"Dossier introuvable : {log_root}")

    runs = []
    for d in log_root.iterdir():
        if not d.is_dir():
            continue

        # Matcher : PPO_gamma_0.99_1
        m = re.match(r"^PPO_gamma_([0-9.]+)_(\d+)$", d.name)
        if m:
            gamma = float(m.group(1))
            run_id = int(m.group(2))
            runs.append((gamma, run_id, d))

    if not runs:
        raise FileNotFoundError(
            f"Aucun dossier PPO_gamma_*_<n> trouvé dans {log_root}\n"
            f"Dossiers présents : {[d.name for d in log_root.iterdir() if d.is_dir()]}"
        )

    runs.sort(key=lambda x: (x[0], x[1]))
    return runs


def load_scalar(run_path: Path, tag: str):
    """Charge un scalaire TensorBoard. Retourne (steps, values) ou (None, None)."""
    ea = EventAccumulator(str(run_path))
    ea.Reload()

    scalar_tags = ea.Tags().get("scalars", [])
    if tag not in scalar_tags:
        return None, None

    events = ea.Scalars(tag)
    if not events:
        return None, None

    steps = [e.step for e in events]
    values = [e.value for e in events]
    return steps, values


def smooth(values, window=200):
    """Lissage par moyenne glissante."""
    return pd.Series(values).rolling(window=window, min_periods=1).mean().tolist()


def plot_tag(runs, tag: str, out_dir: Path, smooth_window: int = 200):
    """Trace et sauvegarde un graphe pour un tag donné."""
    fig, axes = plt.subplots(1, 2, figsize=(16, 5))
    fig.suptitle(f"{tag} — comparaison des gamma", fontsize=13)

    found_any = False

    for gamma, run_id, run_path in runs:
        steps, values = load_scalar(run_path, tag)
        if steps is None:
            print(f"  [manquant] tag='{tag}' dans {run_path.name}")
            continue

        smoothed = smooth(values, window=smooth_window)
        label = f"γ={gamma}"

        # Graphe brut
        axes[0].plot(steps, values, alpha=0.4, label=label)
        # Graphe lissé
        axes[1].plot(steps, smoothed, label=label)

        found_any = True

    if not found_any:
        plt.close()
        print(f"Tag '{tag}' introuvable dans tous les runs — graphe ignoré.")
        return

    for ax, title in zip(axes, ["Brut (raw)", f"Lissé (window={smooth_window})"]):
        ax.set_xlabel("Timesteps")
        ax.set_ylabel(tag)
        ax.set_title(title)
        ax.grid(True)
        ax.legend()

    plt.tight_layout()

    save_path = out_dir / f"{sanitize_filename(tag)}.png"
    plt.savefig(save_path, dpi=200)
    plt.close()
    print(f"Sauvegardé : {save_path}")


def main():
    root = Path(__file__).resolve().parents[2]
    log_root = root / "logs"
    out_dir = root / "compare_gamma_plots"
    out_dir.mkdir(exist_ok=True)

    runs = get_gamma_runs(log_root)
    print(f"{len(runs)} run(s) trouvé(s) :")
    for gamma, run_id, path in runs:
        print(f"  γ={gamma}  run_id={run_id}  → {path.name}")

    tags_to_plot = [
        "custom/step_reward",
        "train/loss",
        "train/policy_gradient_loss",
        "train/value_loss",
        "train/entropy_loss",
    ]

    print()
    for tag in tags_to_plot:
        plot_tag(runs, tag, out_dir, smooth_window=200)

    print(f"\nTous les graphes sont dans : {out_dir}")


if __name__ == "__main__":
    main()