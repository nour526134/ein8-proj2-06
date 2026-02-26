from fastapi import APIRouter
from pydantic import BaseModel
import numpy as np
from stable_baselines3 import PPO


router = APIRouter(prefix="/decision", tags=["decision"])


# Chargement du modèle une seule fois au démarrage
model = PPO.load("models/ppo_modal_decision")


class DecisionRequest(BaseModel):
    dist_station: float          
    dist_dest: float  
    traffic: float
    eta_car_dest: float           
    eta_car_station: float             
    train_wait: float      
    train_trip: int             



@router.post("")
def decide(req: DecisionRequest):
    # Convertir la requête en vecteur numpy pour le modèle
    obs = np.array([
        req.dist_station,
        req.dist_dest,
        req.traffic,
        req.eta_car_dest,
        req.eta_car_station,
        req.train_wait,
        req.train_trip
    ], dtype=np.float32)

    # Le modèle PPO prend la décision
    action, _ = model.predict(obs, deterministic=True)
    action = int(action)

    return {
        "action": action,
        "label": "PARK_AND_RIDE" if action == 1 else "DRIVE"
    }