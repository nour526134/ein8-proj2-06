import os
import re
import matplotlib.pyplot as plt
from tensorboard.backend.event_processing.event_accumulator import EventAccumulator

def latest_ppo_dir(log_root="logs"):
    ppo_dirs = []
    for d in os.listdir(log_root):
        m = re.match(r"^PPO_(\d+)$", d)
        if m:
            ppo_dirs.append((int(m.group(1)), d))

    if not ppo_dirs:
        raise FileNotFoundError("Aucun dossier PPO_<num> trouvé dans logs/")

    ppo_dirs.sort(key=lambda x: x[0])
    return os.path.join(log_root, ppo_dirs[-1][1])

def main():
    log_dir = latest_ppo_dir("logs")
    print("Using log directory:", log_dir)

    ea = EventAccumulator(log_dir)
    ea.Reload()

    scalar_tags = ea.Tags().get("scalars", [])
    print("\nAvailable scalar tags:")
    for t in scalar_tags:
        print(" -", t)

    candidates = ["rollout/ep_rew_mean", "eval/mean_reward", "train/mean_reward"]
    tag = next((t for t in candidates if t in scalar_tags), None)

    if tag is None:
        raise KeyError("Aucun tag reward trouvé dans ce run (scalars vides ou tag différent).")

    events = ea.Scalars(tag)
    steps = [e.step for e in events]
    values = [e.value for e in events]

    plt.plot(steps, values)
    plt.xlabel("Timesteps")
    plt.ylabel(tag)
    plt.title("Reward curve")
    plt.grid(True)
    plt.savefig("reward_curve.png", dpi=200)
    plt.show()

if __name__ == "__main__":
    main()