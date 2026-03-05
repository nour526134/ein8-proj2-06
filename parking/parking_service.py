
import json
import time
from pathlib import Path
from typing import Dict, Any, Optional
import numpy as np
from parking.osrm_client import OSRMClient
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from src.gtfs_service import GTFSService
import pandas as pd
import math
def haversine_m(lat1, lon1, lat2, lon2) -> float:
    """Distance Haversine en mètres."""
    R = 6371000.0
    phi1 = np.radians(lat1)
    phi2 = np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlambda = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(phi1) * np.cos(phi2) * np.sin(dlambda / 2) ** 2
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))
    return float(R * c)

def get_parkings(data_path: str = "data/osm/parkings.csv"):
    """Charge les parkings"""
    base_dir = Path.cwd()
    file_path = base_dir / data_path
    
    if not file_path.exists():
        return []
    
    df = pd.read_csv(file_path)
    parkings = df.to_dict('records')
    return parkings
import pandas as pd
from pathlib import Path
from typing import Dict, Any

def load_stops_to_dict(file_path: str = "data/gtfs_bordeaux/stops.csv") -> Dict[str, Dict[str, Any]]:
    """
    Charge un fichier CSV de stops et retourne un dictionnaire avec:
    clé: stop_id
    valeur: {'name': stop_name, 'lat': stop_lat, 'lon': stop_lon}
    
    Args:
        file_path: Chemin vers le fichier CSV
    
    Returns:
        Dictionnaire avec les stops formatés
    """
    # Résoudre le chemin absolu
    base_dir = Path.cwd()
    full_path = base_dir / file_path
        
    if not full_path.exists():
        print(f"Fichier non trouvé: {full_path}")
        return {}
    df = pd.read_csv(full_path)
    stops_dict = {}
    for _, row in df.iterrows():
        stop_id = str(row['stop_id'])  
        stops_dict[stop_id] = {
            'name': row['stop_name'],
            'lat': float(row['stop_lat']),
            'lon': float(row['stop_lon'])
        }
    return stops_dict
class ParkingServiceOSRM:
    """
    Pour chaque station:
      - choisir 1 parking (le plus proche via Haversine)
    """

    def __init__(
        self,
        use_public_osrm: bool = True,
        local_osrm_url: Optional[str] = None,
        cache_dir: str = "data/cache2",
        profile: str = "walking",    
        rate_limit_s: float = 0.3,
        precompute: bool = True,
    ):
        self.parkings = get_parkings()
        self.stations = load_stops_to_dict()
        if not Path(cache_dir).is_absolute():
            project_root = Path(__file__).parent.parent
            self.cache_dir = project_root / cache_dir
        else:
            self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.osrm = OSRMClient(
            use_public_api=use_public_osrm,
            local_url=local_osrm_url,
            profile=profile,
            rate_limit_s=rate_limit_s,
        )
        self.route_cache_file = self.cache_dir / "parking_cache.json"
        self.osrm.load_cache(self.route_cache_file)

        self.best_parking_by_station: Dict[str, Dict[str, Any]] = {}

        self.best_file = self.cache_dir / "station_best_parking.json"
        if precompute:
            self._precompute_best()

    def _closest_parking_haversine(self, station: Dict[str, Any]) -> Dict[str, Any]:
        """Retourne le parking le plus proche via Haversine."""
        slat, slon = station["lat"], station["lon"]
        best_p = None
        best_d = float("inf")

        for p in self.parkings:
            d = haversine_m(slat, slon, p["lat"], p["lon"])
            if d < best_d:
                best_d = d
                best_p = p

        return best_p

    def _haversine(self, lat1, lon1, lat2, lon2) -> float:
        R = 6371
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
        return R * 2 * math.asin(math.sqrt(a))
    def _precompute_best(self):
        if self.best_file.exists():
            with open(self.best_file, "r", encoding="utf-8") as f:
                self.best_parking_by_station = json.load(f)
            return

        start = time.time()
        out = {}
        failed = 0
        WALK_SPEED_KMH = 5.0

        for s in self.stations:
            sid = s
            p = self._closest_parking_haversine(self.stations[s])
            if p is None:
                failed += 1
                continue

            dist_km = self._haversine(
                self.stations[s]["lat"], self.stations[s]["lon"],
                p["lat"], p["lon"]
            )
            walk_time_min = (dist_km / WALK_SPEED_KMH) * 60

            out[sid] = {
                "station_id": sid,
                "parking_id": p["id"],
                "parking_lat": p["lat"],
                "parking_long": p["lon"],
                "parking_name": p.get("name", p["id"]),
                "walk_time_min": walk_time_min,
                "walk_distance_m": dist_km * 1000,
            }

        self.best_parking_by_station = out
        with open(self.best_file, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2, ensure_ascii=False)

        print(f"Terminé en {time.time() - start:.1f}s")
    # ---------- API ----------
    def get_best_parking_for_station(self,station_id):
        di=self.best_parking_by_station.get(station_id)
        return {
            "parking_id":di["parking_id"],
            "lat":di["parking_lat"],
            "lon":di["parking_long"]
        }
    def get_walk_time_station_parking(self,station_id):
        return self.best_parking_by_station.get(station_id)["walk_time_min"]