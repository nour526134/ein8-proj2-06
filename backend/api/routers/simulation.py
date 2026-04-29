from rl.env.park_ride_env import minutes_to_time_str
from rl.simulators.car_simulator import CarSimulator
from  src.gtfs_service import GTFSService  
from fastapi import APIRouter, HTTPException
import numpy as np


router = APIRouter(prefix="/simulation", tags=["simulation"])


car_simulator = CarSimulator()
gtfs = GTFSService("data/gtfs_bordeaux")
      


@router.post("/reset")
def post_car_simulator(seed: int = None):
    car_simulator.reset(seed=seed)
    return {
        "status": "ok",
        "metrics": car_simulator.get_metrics(),
        "closest_station_id": car_simulator.get_closest_station_id(),
        "dest_id": car_simulator.get_dest_id(),
        
    }


@router.post("/step")
def post_advance(dt_min: float = 1.0):
    car_simulator.advance(dt_min)
    dist = car_simulator.get_dist_to_station_km()
    return {
        "metrics": car_simulator.get_metrics(),
        "closest_station_id": car_simulator.closest_station_id,
        "near_station": dist <= 2.0,  
    }
    

@router.get("/state")
def get_state():
    metrics = car_simulator.get_metrics()
    station_id = car_simulator.get_closest_station_id()
    time_str = minutes_to_time_str(metrics["time_min"])
    trains = gtfs.get_next_trains( stop_id=station_id, current_time=time_str,limit=3)
    
    return {
        "metrics": metrics,
        "station_id": station_id,
        "dest_id": car_simulator.get_dest_id(),
        "time_str": time_str,
        "next_trains": trains.to_dict(orient="records") if len(trains) > 0 else [],
        "car_time_to_dest": car_simulator.car_time_to_dest(),
        "car_time_to_station": car_simulator.car_time_to_station(),
    }


    
    
