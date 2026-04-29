from fastapi import FastAPI

from simu.sumo_car_simulator import CarSimulator as SumoSimulator
from backend.api.routers.trains import router as trains_router
from backend.api.routers.decision import router as decision_router
from backend.api.routers.simulation import router as simulation_router
from backend.api.routers.realtime import router as realtime_router




app = FastAPI(title="Modal Shift API", version="0.1.0")

@app.get("/health")
def health():
    return {"status": "ok"}


sumo_sim = SumoSimulator(gui=False)
sumo_initialized = False

@app.post("/sumo/start")
async def sumo_start(seed: int = 42):
    """Lance une nouvelle simulation SUMO"""
    global sumo_initialized
    try:
        sumo_sim.reset(seed=seed)
        sumo_initialized = True
        
        # Récupère le trajet complet dès le départ
        route_points = sumo_sim.get_route_coordinates()
        position     = sumo_sim.get_position()
        
        return {
            "status":       "started",
            "position":     position,
            "route_points": route_points,  # ← trajet complet pour Flutter
            "dist_km":      sumo_sim.dist,
            "time_to_dest": sumo_sim.time_to_dest_min,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/sumo/step")
async def sumo_step(dt_min: float = 1.0):
    """Avance la simulation d'un pas et retourne la position"""
    if not sumo_initialized:
        return {"status": "error", "message": "SUMO pas initialisé"}
    
    sumo_sim.advance(dt_min=dt_min)
    position = sumo_sim.get_position()
    metrics  = sumo_sim.get_metrics()
    
    # Vérifie si on est proche d'une gare
    dist_station = sumo_sim.get_dist_to_station_km()
    near_station = dist_station <= 2.0  # ← seuil de décision
    
    result = {
        "status":       "running" if sumo_sim._is_car_alive() else "finished",
        "position":     position,
        "metrics":      metrics,
        "near_station": near_station,
    }
    
    # Si proche d'une gare → calcule la recommandation RL
    if near_station:
        station    = sumo_sim.get_closest_station()
        # ... calcule obs et appelle le modèle PPO
        result["recommendation"] = {
            "label":    "PARK_AND_RIDE",  # ou DRIVE
            "station":  station,
        }
    
    return result


@app.get("/sumo/route")
async def sumo_get_route():
    """Retourne le trajet complet SUMO en coordonnées GPS"""
    if not sumo_initialized:
        return {"points": []}
    
    return {
        "points": sumo_sim.get_route_coordinates(),
        "current_position": sumo_sim.get_position(),
    }
    
    
app.include_router(trains_router)
app.include_router(decision_router)
app.include_router(simulation_router)
app.include_router(realtime_router)

