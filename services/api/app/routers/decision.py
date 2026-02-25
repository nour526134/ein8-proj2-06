from fastapi import APIRouter
from pydantic import BaseModel


router = APIRouter(prefix="/decision", tags=["decision"])

class DecisionRequest(BaseModel):
    dist_to_station_km: float          
    car_time_to_station_min: float     
    next_train_in_min: float           
    train_delay_min: float             
    train_travel_time_min: float      
    parking_available: int             


def heuristic(req: DecisionRequest) -> int:
    """
    Règle simple :
    - Si parking disponible ET train dans moins de 10 min → PARK_AND_RIDE
    - Sinon → DRIVE
    """
    if req.parking_available == 1 and req.next_train_in_min <= 10:
        return 1  # PARK_AND_RIDE
    return 0      # DRIVE


@router.post("")
def decide(req: DecisionRequest):
    """
    Reçoit la situation de l'utilisateur et retourne la recommandation.
    """
    action = heuristic(req)
    label = "PARK_AND_RIDE" if action == 1 else "DRIVE"
    return {
        "action": action,
        "label": label
    }