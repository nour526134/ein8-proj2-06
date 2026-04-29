import math
import os
import numpy as np
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from src.realtime.transit_realtime_service import TransitRealtimeService
from parking.parking_service import ParkingServiceStatic
from rl.simulators.car_simulator import haversine_m
from stable_baselines3 import PPO
import datetime


router = APIRouter(prefix="/realtime", tags=["realtime"])

parking_svc = ParkingServiceStatic()
transit = TransitRealtimeService()
transit.refresh()  # Charger les données GTFS-RT au démarrage
model    = PPO.load("models/ppo_modal_decision")
stations = transit.gtfs.load_stops()


# ── Modèle de données reçues depuis Streamlit en temps reel ────────────────────────────────
class RealTimeRequest(BaseModel):
    lat:       float  # latitude GPS actuelle du conducteur
    lon:       float  # longitude GPS actuelle du conducteur
    dest_lat:  float  # latitude GPS de la destination finale
    dest_lon:  float  # longitude GPS de la destination finale
    speed_kmh: float  # vitesse actuelle du conducteur (depuis GPS)
    time_str:  str    # heure actuelle format "HH:MM:SS"


# ── Endpoint principal ───────────────────────────────────────────────────────
@router.post("/state")
def get_realtime_state(req: RealTimeRequest):
   
    closest_station_id, dist_station_km = _find_closest_station(
        req.lat, req.lon
    )
    if closest_station_id is None:
        raise HTTPException(status_code=404, detail="Aucune gare trouvée")

   
    dest_station_id, _ = _find_closest_station(req.dest_lat, req.dest_lon)

    train_wait = transit.train_wait_time_from_trips_realtime(
        closest_station_id,
        dest_station_id,
        req.time_str
    )
    
    train_trip = transit.gtfs.train_trip_time(closest_station_id, dest_station_id)
    if not math.isfinite(train_wait):
        train_wait = float(60.0)  # 60 min par défaut

    if not math.isfinite(train_trip):
        train_trip = float(30.0)  # 30 min par défaut
    
    
    dist_dest_km = haversine_m(
        req.lat, req.lon,
        req.dest_lat, req.dest_lon
    )/ 1000.0
    speed_kmh       = max(req.speed_kmh, 5.0) # éviter division par zéro
    eta_car_dest    = dist_dest_km / speed_kmh * 60
    eta_car_station = dist_station_km / speed_kmh * 60

    
    traffic = float(max(0.0, min(1.0, 1.0 - (req.speed_kmh / 90.0))))

    
    
    
    try:
        h, m, s = map(int, req.time_str.split(":"))
        time_min = h * 60 + m + s / 60
    except Exception:
        time_min = 8 * 60  # fallback 8h
    time_of_day = (time_min % (24 * 60)) / (24 * 60)

    
    station_dict = {
        "id":  closest_station_id,
        "lat": stations[closest_station_id]["lat"],
        "lon": stations[closest_station_id]["lon"],
    }
    parking = parking_svc.get_best_parking_for_station(closest_station_id)
    taux_parking = 0.5  
    
    dist_parking_km = 0.0
    eta_car_parking = 0.0
    if parking is not None:
        dist_parking_km = haversine_m(
            req.lat, req.lon,
            parking.get("parking_lat", req.lat),
            parking.get("parking_lon", parking.get("parking_long", req.lon))
        ) / 1000.0
        eta_car_parking = dist_parking_km / max(req.speed_kmh, 5.0) * 60

    
    obs = np.array([
        min(dist_dest_km / 40.0,       1.0),   
        float(time_of_day),                     
        min(dist_parking_km / 15.0,    1.0),   
        float(traffic),                         
        min(eta_car_dest / 120.0,      1.0),  
        min(eta_car_parking / 120.0,   1.0),   
        min(train_wait / 120.0,        1.0),   
        min(train_trip / 120.0,        1.0),   
        float(taux_parking),                    
    ], dtype=np.float32)

    
    action, _ = model.predict(obs, deterministic=True)
    action = int(action)

    parking_info = None
    if action == 1:
        parking = parking_svc.get_best_parking_for_station(closest_station_id)
        walk_time = parking_svc.get_walk_time_station_parking(closest_station_id)
        if parking is not None:
            parking_lon = parking.get("parking_lon")
            if parking_lon is None:
                parking_lon = parking.get("parking_long")
            parking_info = {
                "parking_id":    parking.get("parking_id"),
                "name":          parking.get("name", ""),
                "lat":           parking.get("parking_lat"),
                "lon":           parking_lon,
                "walk_time_min": walk_time,
            }
    return {
        "recommendation": {
            "action":  action,
            "label":   "PARK_AND_RIDE" if action == 1 else "DRIVE",
            "message": "🚆 Prenez le train !" if action == 1
                       else "🚗 Continuez en voiture",
        },
        "station1": {
            "id":      closest_station_id,
            "name":    stations[closest_station_id].get("name", ""),
            "lat":     stations[closest_station_id].get("lat"),
            "lon":     stations[closest_station_id].get("lon"),
            "dist_km": round(dist_station_km, 2),
            "eta_min": round(eta_car_station, 1),
        },
        "station2": {
            "id":      dest_station_id,
            "name":    stations[dest_station_id].get("name", ""),
            "lat":     stations[dest_station_id].get("lat"),
            "lon":     stations[dest_station_id].get("lon"),
        },
        "trains": {
        "train_wait_min": _safe_float(train_wait, 60.0),
        "train_trip_min": _safe_float(train_trip, 30.0),
        },
        "car": {
            "eta_dest_min": _safe_float(eta_car_dest, 999.0),
            "traffic":      _safe_float(traffic, 0.5),
        },
	"parking" : parking_info,
        
    }



def _find_closest_station(lat: float, lon: float):
    """
    Parcourt toutes les gares GTFS.
    Retourne (station_id, distance_km) de la plus proche.
    """
    min_dist   = float("inf")
    closest_id = None

    for sid, sdata in stations.items():
        dist = haversine_m(lat, lon, sdata["lat"], sdata["lon"])/ 1000.0
        if dist < min_dist:
            min_dist   = dist
            closest_id = sid

    return closest_id, min_dist



def _safe_float(value: float, default: float) -> float:
    """Remplace inf/nan par une valeur par défaut."""
    if not math.isfinite(value):
        return default
    return round(value, 2)
