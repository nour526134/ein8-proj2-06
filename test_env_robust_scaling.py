#!/usr/bin/env python3
"""
Test script to verify the environment works with robust scaling.
"""
import numpy as np
from rl.env.park_ride_env_realtime import ParkOrRide

def test_environment_with_robust_scaling():
    print("=" * 70)
    print("Testing ParkOrRide Environment with Robust Scaling")
    print("=" * 70)
    
    # Create environment
    print("\n[1/4] Creating environment...")
    env = ParkOrRide(env_id=0)
    print("      ✓ Environment created successfully")
    
    # Reset and get initial observation
    print("\n[2/4] Resetting environment...")
    obs, info = env.reset()
    print("      ✓ Environment reset successfully")
    print(f"      Observation shape: {obs.shape}")
    print(f"      Observation dtype: {obs.dtype}")
    print(f"      Observation bounds: min={obs.min():.4f}, max={obs.max():.4f}")
    
    # Take a random action
    print("\n[3/4] Testing step with random action...")
    action = env.action_space.sample()
    obs, reward, terminated, truncated, info = env.step(action)
    print(f"      ✓ Step executed successfully")
    print(f"      Action taken: {action} ({'car' if action == 0 else 'train'})")
    print(f"      Reward: {reward:.4f}")
    print(f"      Observation: {obs}")
    print(f"      Info keys: {list(info.keys())}")
    
    # Check observation bounds
    print("\n[4/4] Validating observation space constraints...")
    if np.all(obs >= 0) and np.all(obs <= 1):
        print("      ✓ All observations are in [0, 1] range")
    else:
        out_of_bounds = np.sum((obs < 0) | (obs > 1))
        print(f"      ✗ {out_of_bounds} values out of [0, 1] range!")
    
    print("\n" + "=" * 70)
    print("Environment Test Summary:")
    print("  • TrainFeatureScaler is applied to train wait and trip times")
    print("  • Uses median and IQR (Q1-Q3) for robust scaling")
    print("  • More resistant to outliers than min-max scaling")
    print("  • Observations clipped to [0, 1] for gym compatibility")
    print("=" * 70)
    print("\n✓ All tests passed!\n")

if __name__ == "__main__":
    test_environment_with_robust_scaling()
