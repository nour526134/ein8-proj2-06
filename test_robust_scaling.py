#!/usr/bin/env python3
"""
Test script to verify robust scaling for train features.
"""
import numpy as np
from rl.env.park_ride_env_realtime import TrainFeatureScaler
from src.gtfs_service import GTFSService

def test_robust_scaling():
    print("=" * 60)
    print("Testing Robust Scaling for Train Features")
    print("=" * 60)
    
    # Initialize GTFS service
    gtfs = GTFSService()
    
    # Initialize the robust scaler
    print("\n[INFO] Initializing TrainFeatureScaler...")
    scaler = TrainFeatureScaler(gtfs)
    
    print("\n--- Scaler Wait Statistics ---")
    print(f"  • Median: {scaler.scaler_wait.center_[0]:.2f} minutes")
    print(f"  • Q1: {scaler.scaler_wait.center_[0] - (scaler.scaler_wait.scale_[0] / 2):.2f} minutes")
    print(f"  • Q3: {scaler.scaler_wait.center_[0] + (scaler.scaler_wait.scale_[0] / 2):.2f} minutes")
    print(f"  • IQR: {scaler.scaler_wait.scale_[0]:.2f} minutes")
    
    print("\n--- Scaler Trip Statistics ---")
    print(f"  • Median: {scaler.scaler_trip.center_[0]:.2f} minutes")
    print(f"  • Q1: {scaler.scaler_trip.center_[0] - (scaler.scaler_trip.scale_[0] / 2):.2f} minutes")
    print(f"  • Q3: {scaler.scaler_trip.center_[0] + (scaler.scaler_trip.scale_[0] / 2):.2f} minutes")
    print(f"  • IQR: {scaler.scaler_trip.scale_[0]:.2f} minutes")
    
    # Test scaling with various values
    print("\n--- Testing Robust Scaling (Wait Times) ---")
    test_waits = [0, 30, 60, 90, 120, 150]
    print(f"{'Value (min)':<15} {'Scaled [0,1]':<15}")
    print("-" * 30)
    for wait_val in test_waits:
        scaled = scaler.scale_wait(wait_val)
        print(f"{wait_val:<15} {scaled:<15.4f}")
    
    print("\n--- Testing Robust Scaling (Trip Times) ---")
    test_trips = [15, 30, 60, 90, 120, 150, 180]
    print(f"{'Value (min)':<15} {'Scaled [0,1]':<15}")
    print("-" * 30)
    for trip_val in test_trips:
        scaled = scaler.scale_trip(trip_val)
        print(f"{trip_val:<15} {scaled:<15.4f}")
    
    print("\n✓ Robust scaling test completed successfully!")
    print("\nAdvantages of Robust Scaling:")
    print("  • Uses median and IQR instead of min/max")
    print("  • More resistant to outliers")
    print("  • Better distribution for skewed data")
    print("=" * 60)

if __name__ == "__main__":
    test_robust_scaling()
