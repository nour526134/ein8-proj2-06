from fastapi import APIRouter
from pydantic import BaseModel
import numpy as np
from stable_baselines3 import PPO
import datetime


router = APIRouter(prefix="/decision", tags=["decision"])


model = PPO.load("models/ppo_modal_decision")
#model = None


class DecisionRequest(BaseModel):
    dist_dest:       float
    time_of_day:     float  
    dist_parking:    float
    traffic:         float
    eta_car_dest:    float
    eta_car_parking: float
    train_wait:      float
    train_trip:      float
    taux_parking:    float            



@router.post("")
def decide(req: DecisionRequest):
    # Convertir la requête en vecteur numpy pour le modèle
    obs = np.array([
        req.dist_dest,
        req.time_of_day,
        req.dist_parking,
        req.traffic,
        req.eta_car_dest,
        req.eta_car_parking,
        req.train_wait,
        req.train_trip,
        req.taux_parking,
    ], dtype=np.float32)

    # Le modèle PPO prend la décision
    action, _ = model.predict(obs, deterministic=True)
    action = int(action)

    return {
        "action": action,
        "label": "PARK_AND_RIDE" if action == 1 else "DRIVE"
    }
