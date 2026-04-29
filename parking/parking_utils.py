"""
parking/parking_utils.py
========================
Fonctions pures utilitaires pour le service parking.
Source : API ODS DataHub Bordeaux Métropole (sans clé API).
Aucune variable globale — tout passe en paramètre.
"""

from __future__ import annotations

import json
import math
import urllib.request
import urllib.error
from typing import Optional
import pandas as pd
import numpy as np

import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.gtfs_service import GTFSService

ODS_URL = (
    "https://datahub.bordeaux-metropole.fr/api/explore/v2.1"
    "/catalog/datasets/st_park_p/records"
    "?limit=100&timezone=Europe%2FParis"
)

def _to_int(value, default: int = 0) -> int:
    """
    Convertit proprement une valeur en int.
    - None, "", "N/A", NaN → default
    - "42.7" → 42  (via float intermédiaire)
    - Lève TypeError si la valeur est un type non convertible
    """
    if value is None:
        return default
    if isinstance(value, float):
        if math.isnan(value):
            return default
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if stripped in ("", "N/A", "None", "null", "-"):
            return default
        try:
            return int(float(stripped))  # gère "42.7" → 42
        except ValueError:
            return default
    # bool est un sous-type de int en Python, déjà couvert plus haut
    raise TypeError(f"_to_int: type non supporté {type(value)!r} pour la valeur {value!r}")
def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance vol d'oiseau entre deux points GPS (km)."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1))
         * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


def walk_time_min(dist_km: float, walk_speed_kmh: float) -> float:
    """Temps de marche en minutes pour une distance et une vitesse données."""
    return round((dist_km / walk_speed_kmh) * 60.0, 2)


def fetch_parkings(timeout: int = 10) -> list[dict]:
    """
    Récupère les records parking depuis l'API ODS du DataHub Bordeaux Métropole.
    Aucune clé API requise. Rafraîchissement toutes les 2min30 côté serveur.

    Returns
    -------
    list[dict] : liste de records bruts ODS, ou [] en cas d'erreur.
    """
    try:
        req = urllib.request.Request(
            ODS_URL,
            headers={"User-Agent": "ParkOrRide/1.0"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("results", [])

    except urllib.error.HTTPError as e:
        print(f"[fetch_parkings] HTTP {e.code} sur {ODS_URL} : {e.reason}")
        return []
    except urllib.error.URLError as e:
        print(f"[fetch_parkings] Connexion impossible : {e.reason}")
        return []
    except Exception as e:
        print(f"[fetch_parkings] Erreur inattendue : {e}")
        return []

def parse_parking(record: dict) -> Optional[dict]:
    """
    Convertit un record ODS Bordeaux Métropole en dict parking normalisé.

    Champs ODS réels :
        geo_point_2d → {"lat": float, "lon": float}
        gid          → identifiant
        nom          → nom du parking
        libres       → places libres  (et non "nb_libre")
        total        → places totales (et non "nbrpl")
        etat         → "LIBRE" | "COMPLET" | "FERME" (majuscules)
        exploit      → gestionnaire   (et non "gestionnai")
        connecte     → 1 si données temps réel disponibles

    Returns
    -------
    dict avec : parking_id, nom, lat, lon, nb_libre, nb_total,
                etat, ouvert, gestionnaire
    None si les coordonnées sont manquantes.
    """
    geo = record.get("geo_point_2d") or {}
    lat = geo.get("lat")
    lon = geo.get("lon")

    if lat is None or lon is None:
        return None

    etat = str(record.get("etat", "")).strip().upper()

    return {
        "parking_id":   str(record.get("gid", "")),
        "nom":          str(record.get("nom", "")),
        "lat":          float(lat),
        "lon":          float(lon),
        "nb_libre":     _to_int(record.get("libres")),    # ← "libres" et non "nb_libre"
        "nb_total":     _to_int(record.get("total")),     # ← "total" et non "nbrpl"
        "etat":         etat,
        "ouvert":       etat not in ("FERME", "FERMÉ"),   # ← majuscules
        "gestionnaire": str(record.get("exploit", "")),   # ← "exploit" et non "gestionnai"
        "connecte":     bool(record.get("connecte", 0)),  # données temps réel dispos
    }




def compute_station_parking_distances(
    static_path: str = "data/parkings_static.csv",
) -> np.ndarray:
    """
    Calcule toutes les distances gare↔parking depuis :
      - les gares  : GTFSService.load_stops()
      - les parkings : snapshot statique CSV

    Returns
    -------
    np.ndarray : tableau 1D de toutes les distances en km
    """
    # Chargement gares
    gtfs = GTFSService()
    stops = gtfs.load_stops()  # dict {stop_id: {lat, lon, name}}
    stations = list(stops.values())

    # Chargement parkings statiques
    df = pd.read_csv(static_path)
    df = df.dropna(subset=["lat", "lon"])
    parkings = df[["lat", "lon"]].to_dict(orient="records")

    if not stations or not parkings:
        raise ValueError("Aucune gare ou parking chargé")

    # Toutes les distances gare↔parking
    distances = []
    for s in stations:
        for p in parkings:
            d = haversine_km(s["lat"], s["lon"], p["lat"], p["lon"])
            distances.append(d)

    arr = np.array(distances)
    return arr