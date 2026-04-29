import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
import numpy as np
import pandas as pd
from stable_baselines3 import PPO


from rl.training.config import PPOConfig
from rl.env.park_ride_env_realtime import ParkOrRide


def compute_expected_action(env, info):

    try:
        car_time = float(env.sim.car_time_to_dest())

        train_time = (
            float(info.get("car_parking_time"))
            # float(info.get("car_time_to_parking_min"))
            + float(info["walk_time"])
            # + float(info["train_wait_min"])
            + float(info["train_trip_min"])
        )

    except KeyError:
        print("⚠️ Episode ignoré (info incomplet):", info)
        return None, None, None

    if car_time <= train_time:
        return 0, car_time, train_time
    else:
        return 1, car_time, train_time


def evaluate(model_path: str, n_episodes: int = 200):

    env = ParkOrRide()
    model = PPO.load(model_path)

    results = []

    for episode in range(n_episodes):

        obs, info = env.reset(seed=episode)

        if info.get("reset") != "success":
            continue

        action, _ = model.predict(obs, deterministic=True)

        obs, reward, terminated, truncated, info = env.step(action)

        expected_action, car_time, train_time = compute_expected_action(env, info)

        if expected_action is None:
            continue

        correct = int(action == expected_action)
        regret = abs(car_time - train_time) if not correct else 0.0
        print("car_time:", car_time, "train_time:", train_time)
        results.append({
            "episode": episode,

            "traffic": env.current_metrics.get("traffic"),
            "dist_station": env.current_metrics.get("dist_to_station_km"),
            "dist_dest": env.current_metrics.get("dist_to_dest_km"),

            "car_time": car_time,
            "train_time": train_time,

            "predicted_action": int(action),
            "expected_action": int(expected_action),
            "correct": correct,
            "regret": regret,

            "reward": reward
        })

    df = pd.DataFrame(results)
    print("Actions prédites uniques :", df["predicted_action"].unique())
    print(df["predicted_action"].value_counts())
   
    accuracy = df["correct"].mean()
    mean_reward = df["reward"].mean()
    std_reward = df["reward"].std()

    mean_regret = df["regret"].mean()
    max_regret = df["regret"].max()

    confusion = pd.crosstab(
        df["expected_action"],
        df["predicted_action"],
        rownames=["Actual"],
        colnames=["Predicted"]
    )

    print("\n====== EVALUATION ======")
    print(f"Episodes: {len(df)}")
    print(f"Accuracy: {accuracy * 100:.2f}%")
    print(f"Mean reward: {mean_reward:.2f}")
    print(f"Std reward: {std_reward:.2f}")
    print(f"Mean regret: {mean_regret:.2f}")
    print(f"Max regret: {max_regret:.2f}")
    
    print("\nConfusion Matrix:")
    print(confusion)


    output_file = "evaluation_results.xlsx"

    with pd.ExcelWriter(output_file) as writer:
        df.to_excel(writer, sheet_name="results", index=False)

        summary_df = pd.DataFrame([{
            "accuracy": accuracy,
            "mean_reward": mean_reward,
            "std_reward": std_reward,
            "mean_regret": mean_regret,
            "max_regret": max_regret
        }])

        summary_df.to_excel(writer, sheet_name="summary", index=False)

    print(f"\nFichier Excel généré: {output_file}")

    return {
        "accuracy": accuracy,
        "mean_reward": mean_reward,
        "mean_regret": mean_regret
    }


def main():
    cfg = PPOConfig()
    model_path = f"{cfg.models_dir}/{cfg.model_name}.zip"

    evaluate(model_path=model_path, n_episodes=200)


if __name__ == "__main__":
    main()