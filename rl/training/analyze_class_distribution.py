"""
Analyze the actual distribution of optimal actions in the environment.
This helps understand if action 0 dominance is:
1. Natural (routes are short, car is naturally faster)
2. A bias from training data
3. Policy collapse
"""
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import numpy as np
import pandas as pd
from rl.env.park_ride_env_realtime import ParkOrRide
from rl.training.config import PPOConfig


def compute_expected_action(env, info):
    """What action SHOULD be taken (optimal choice based on travel times)"""
    try:
        car_time = float(env.sim.car_time_to_dest())
        train_time = (
            float(info.get("car_parking_time", 0))
            + float(info["walk_time"])
            + float(info["train_wait_min"])
            + float(info["train_trip_min"])
        )
    except (KeyError, TypeError, ValueError):
        return None, None, None

    if car_time <= train_time:
        return 0, car_time, train_time
    else:
        return 1, car_time, train_time


def analyze_distribution(n_episodes=500):
    """Sample many episodes and analyze the natural distribution of optimal actions"""
    env = ParkOrRide()
    
    results = []
    skipped = 0
    
    for episode in range(n_episodes):
        obs, info = env.reset(seed=episode)
        
        if info.get("reset") != "success":
            skipped += 1
            continue
        
        # Take a dummy action (action 0) to get step info with times
        action = 0
        obs, reward, terminated, truncated, info = env.step(action)
        
        # Now compute what the OPTIMAL action should have been
        expected_action, car_time, train_time = compute_expected_action(env, info)
        
        if expected_action is None:
            skipped += 1
            continue
        
        results.append({
            "episode": episode,
            "expected_action": expected_action,
            "optimal_action": "Car" if expected_action == 0 else "Train",
            "car_time": car_time,
            "train_time": train_time,
            "time_difference": abs(car_time - train_time),
            "car_faster": 1 if car_time < train_time else 0,
            "traffic": env.current_metrics.get("traffic", 0),
            "dist_to_station": env.current_metrics.get("dist_to_station_km", 0),
            "dist_to_dest": env.current_metrics.get("dist_to_dest_km", 0),
            "reward_received": reward,
        })
    
    print(f"Valid episodes: {len(results)}/{n_episodes}")
    print(f"Skipped episodes: {skipped}/{n_episodes}")
    
    if len(results) == 0:
        print("❌ No valid episodes found!")
        return None
    
    df = pd.DataFrame(results)
    
    print("\n" + "="*60)
    print("CLASS DISTRIBUTION ANALYSIS")
    print("="*60)
    
    print(f"\nTotal episodes analyzed: {len(df)}")
    
    action_counts = df["expected_action"].value_counts()
    print("\n--- Optimal Action Distribution ---")
    print(f"Action 0 (Car):   {action_counts.get(0, 0)} ({action_counts.get(0, 0)/len(df)*100:.1f}%)")
    print(f"Action 1 (Train): {action_counts.get(1, 0)} ({action_counts.get(1, 0)/len(df)*100:.1f}%)")
    
    car_faster = df["car_faster"].sum()
    train_faster = len(df) - car_faster
    print(f"\n--- Why car is faster ---")
    print(f"Car is faster: {car_faster} cases ({car_faster/len(df)*100:.1f}%)")
    print(f"Train is faster: {train_faster} cases ({train_faster/len(df)*100:.1f}%)")
    
    print("\n--- Time Differences (when choosing optimally) ---")
    print(f"Mean time difference: {df['time_difference'].mean():.2f} min")
    print(f"Std time difference:  {df['time_difference'].std():.2f} min")
    print(f"Min time difference:  {df['time_difference'].min():.2f} min")
    print(f"Max time difference:  {df['time_difference'].max():.2f} min")
    
    print("\n--- Time comparison when Train is better ---")
    train_better = df[df["expected_action"] == 1]
    if len(train_better) > 0:
        print(f"Avg car time:   {train_better['car_time'].mean():.2f} min")
        print(f"Avg train time: {train_better['train_time'].mean():.2f} min")
        print(f"Avg time saved: {(train_better['car_time'] - train_better['train_time']).mean():.2f} min")
    
    print("\n--- Time comparison when Car is better ---")
    car_better = df[df["expected_action"] == 0]
    if len(car_better) > 0:
        print(f"Avg car time:   {car_better['car_time'].mean():.2f} min")
        print(f"Avg train time: {car_better['train_time'].mean():.2f} min")
        print(f"Avg time saved: {(car_better['train_time'] - car_better['car_time']).mean():.2f} min")
    
    print("\n--- Distance & Traffic Analysis ---")
    print(f"Avg distance to station: {df['dist_to_station'].mean():.2f} km")
    print(f"Avg distance to destination: {df['dist_to_dest'].mean():.2f} km")
    print(f"Avg traffic level: {df['traffic'].mean():.2f}")
    
    # Correlation analysis
    print("\n--- Factors that favor Train (Action 1) ---")
    if len(train_better) > 0:
        print(f"Avg traffic for train choice: {train_better['traffic'].mean():.2f}")
        print(f"Avg distance for train choice: {train_better['dist_to_station'].mean():.2f} km")
    
    return df


if __name__ == "__main__":
    df = analyze_distribution(n_episodes=500)
    if df is not None:
        df.to_csv("class_distribution_analysis.csv", index=False)
        print("\n✅ Analysis saved to: class_distribution_analysis.csv")
    else:
        print("\n❌ Analysis failed - no data to analyze")
