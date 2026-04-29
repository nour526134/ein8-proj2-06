from fastapi import APIRouter
from pydantic import BaseModel
import numpy as np
from stable_baselines3 import PPO
from backend.services.modal_shift_aux import Position, get_route_distance_and_duration

router = APIRouter(prefix="/modal_shift", tags=["modal_shift"])

# Chargement du modèle une seule fois au démarrage (temporairement désactivé)
model = PPO.load("models/ppo_modal_decision")

class ModalShiftRequest(BaseModel):
    origin: Position
    destination: Position

@router.post("")
async def modal_shift(req: ModalShiftRequest):
    """
    Modal shift decision endpoint.
    
    Uses OSRM to calculate distance and ETA from origin to destination,
    then feeds these values to the PPO model for decision making.
    """
    try:
        # Get route information from OSRM
        route_info = await get_route_distance_and_duration(
            origin=req.origin,
            destination=req.destination,
            profile="car"
        )
        
        # Extract distance and duration
        dist_dest_meters = route_info['distance']
        eta_car_dest_seconds = route_info['duration']
        
        # Convert to appropriate units
        dist_dest_km = dist_dest_meters / 1000.0  # meters to km
        eta_car_dest_minutes = eta_car_dest_seconds / 60.0  # seconds to minutes
        
        # Calcul des vraies valeurs à faire plus tard, placeholder en attendant
        obs = np.array([
            0,  # dist_station
            dist_dest_km,  # dist_dest - from OSRM
            0,  # traffic
            eta_car_dest_minutes,  # eta_car_dest - from OSRM
            0,  # eta_car_station
            0,  # train_wait
            0,  # train_trip
        ], dtype=np.float32)

        # Le modèle PPO prend la décision
        action, _ = model.predict(obs, deterministic=True)
        action = int(action)

        return {
            "action": action,
            "label": "PARK_AND_RIDE" if action == 1 else "DRIVE",
            #"route_info": {
            #    "distance_km": dist_dest_km,
            #    "eta_minutes": eta_car_dest_minutes
            #}
        }
    
    except Exception as e:
        return {
            "error": str(e),
            "action": 0,
            #"label": "ERROR"
        }