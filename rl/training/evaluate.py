
import numpy as np
from stable_baselines3 import PPO

from rl.training.config import PPOConfig
from rl.env.modal_env import ModalShiftEnv
from rl.training.metrics import compute_decision_metrics, summarize_metrics


def evaluate(model_path: str, n_episodes: int = 20) -> dict:
    env = ModalShiftEnv()
    model = PPO.load(model_path)

    episode_rewards = []
    correct_list = []
    regret_list = []

    for _ in range(n_episodes): 
        obs, info = env.reset() 
        done = False
        total_reward = 0.0

        while not done:
            action, _ = model.predict(obs, deterministic=True)
            obs, reward, terminated, truncated, info = env.step(action)
            done = terminated or truncated
            total_reward += float(reward)
            car_time = info.get("car_time")
            train_time = info.get("train_time")
            if car_time is not None and train_time is not None:
                m = compute_decision_metrics(
                    car_time=float(car_time),
                    train_time=float(train_time),
                    action=int(action),
                )
                correct_list.append(m["correct"])
                regret_list.append(m["regret"])


        episode_rewards.append(total_reward)

    rewards = np.array(episode_rewards, dtype=np.float32)

    results = {
        "n_episodes": n_episodes,
        "mean_reward": float(rewards.mean()),
        "std_reward": float(rewards.std()),
        "min_reward": float(rewards.min()),
        "max_reward": float(rewards.max()),
    }
    if len(correct_list) > 0:
        met = summarize_metrics(correct_list, regret_list)
        results["decision_accuracy"] = met["accuracy"]
        results["mean_regret"] = met["mean_regret"]
        results["max_regret"] = met["max_regret"]
    else:
        results["decision_accuracy"] = None
        results["mean_regret"] = None
        results["max_regret"] = None

    return results

def main():
    cfg = PPOConfig()
    model_path = f"{cfg.models_dir}/{cfg.model_name}.zip"

    results = evaluate(model_path=model_path, n_episodes=20)

    print("\n   EVALUATION RESULTS   ")
    print(f"Model: {model_path}")
    print(f"Episodes: {results['n_episodes']}")
    print(f"Mean reward: {results['mean_reward']:.2f}")
    print(f"variabilité reward:  {results['std_reward']:.2f}")
    print(f"Min reward:  {results['min_reward']:.2f}")
    print(f"Max reward:  {results['max_reward']:.2f}")
    if results["decision_accuracy"] is not None:
        print("\n   DECISION METRICS  ")
        print(f"Accuracy (bon choix): {results['decision_accuracy']*100:.1f}%")
        print(f"Mean regret (temps perdu moyen): {results['mean_regret']:.2f}")
        print(f"Max regret (pire cas): {results['max_regret']:.2f}")
    else:
        print("\n[Info] metrics.py non calculées : car_time/train_time absents de info dans l'env.")


if __name__ == "__main__":
    main()