import json
import time
from pathlib import Path
from typing import Dict, Any, Optional
import numpy as np
import pandas as pd

import json
import pandas as pd
from pathlib import Path
import numpy as np
import time



def get_parkings(data_path: str = "data/osm/parkings.csv"):
    base_dir = Path.cwd()
    file_path = base_dir / data_path

    if not file_path.exists():
        return []

    df = pd.read_csv(file_path)
    return df.to_dict("records")


def load_stops_to_dict(file_path: str = "data/gtfs_bordeaux/stops.csv"):
    base_dir = Path.cwd()
    full_path = base_dir / file_path

    if not full_path.exists():
        print(f"Fichier non trouvé: {full_path}")
        return {}

    df = pd.read_csv(full_path)

    stops_dict = {}
    for _, row in df.iterrows():
        stop_id = str(row["stop_id"])
        stops_dict[stop_id] = {
            "name": row["stop_name"],
            "lat": float(row["stop_lat"]),
            "lon": float(row["stop_lon"]),
        }

    return stops_dict


class ParkingServiceStatic:
    """
    Service robuste :
    - Associe chaque station à son parking le plus proche
    - Tolérant aux données manquantes
    """

    def __init__(self, cache_dir: str = "data/cache2", precompute: bool = True):

        self.parkings = get_parkings()
        self.stations = load_stops_to_dict()

        project_root = Path(__file__).parent.parent
        self.cache_dir = project_root / cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.best_file = self.cache_dir / "station_best_parking.json"
        self.best_parking_by_station: Dict[str, Dict[str, Any]] = {}

        if precompute:
            self._precompute_best()


    def _haversine(self, lat1, lon1, lat2, lon2) -> float:
        R = 6371000.0
        phi1 = np.radians(lat1)
        phi2 = np.radians(lat2)
        dphi = np.radians(lat2 - lat1)
        dlambda = np.radians(lon2 - lon1)

        a = (
            np.sin(dphi / 2) ** 2
            + np.cos(phi1) * np.cos(phi2) * np.sin(dlambda / 2) ** 2
        )
        return float(2 * R * np.arctan2(np.sqrt(a), np.sqrt(1 - a)))


    def _closest_parking(self, station: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not self.parkings:
            return None

        best = None
        best_d = float("inf")

        for p in self.parkings:
            d = self._haversine(station["lat"], station["lon"], p["lat"], p["lon"])
            if d < best_d:
                best_d = d
                best = p

        return best


    def _precompute_best(self):

        if self.best_file.exists():
            self.best_parking_by_station = json.loads(self.best_file.read_text())
            print("✔ Cache chargé")
            return

        print("⏳ Pré-calcul des parkings...")
        start = time.time()

        out = {}
        failed = 0

        WALK_SPEED_KMH = 5.0

        for station_id, station in self.stations.items():

            if station is None:
                failed += 1
                continue

            p = self._closest_parking(station)

            if p is None:
                failed += 1
                continue

            dist_km = self._haversine(
                station["lat"], station["lon"], p["lat"], p["lon"]
            )

            walk_time = (dist_km / WALK_SPEED_KMH) * 60

            out[station_id] = {
                "station_id": station_id,
                "parking_id": p.get("id"),
                "parking_lat": p.get("lat"),
                "parking_lon": p.get("lon"),
                "walk_time_min": walk_time,
                "distance_m": dist_km * 1000,
            }

        self.best_parking_by_station = out
        self.best_file.write_text(json.dumps(out, indent=2))

        print(f"✔ Done en {time.time() - start:.2f}s | failed={failed}")

   
    def get_best_parking_for_station(self, station_id: str):

        di = self.best_parking_by_station.get(station_id)
        if di is None:
            return None

        parking_lon = di.get("parking_lon")
        if parking_lon is None:
            parking_lon = di.get("parking_long")

        if di.get("parking_lat") is None or parking_lon is None:
            return None
        # if di is None:
        #     print(f"[WARN] parking missing for station={station_id}")
        #     return {
        #         "parking_id": None,
        #         "lat": None,
        #         "lon": None,
        #         "walk_time_min": 9999,
        #     }

        return {
            **di,
            "parking_lon": parking_lon,
        }

    def get_walk_time_station_parking(self, station_id: str) -> float:

        di = self.best_parking_by_station.get(station_id)

        if di is None:
            return 9999.0

        return float(di.get("walk_time_min", 9999.0))
    
