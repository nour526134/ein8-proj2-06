from __future__ import annotations

import time
import csv
import os
from datetime import datetime
from typing import Optional
import math
import numpy as np                       
import pandas as pd
from sklearn.preprocessing import RobustScaler
from parking.parking_utils import compute_station_parking_distances

import sys

from parking.parking_utils import (
    fetch_parkings,
    parse_parking,
    haversine_km,
    walk_time_min
)

DEFAULT_CACHE_TTL   = 150
DEFAULT_WALK_SPEED  = 4.5
DEFAULT_MAX_WALK_KM = 3.0
DEFAULT_MAX_WALK_MIN = 17


class ParkingServiceRT:
    def __init__(
        self,
        cache_ttl: float = DEFAULT_CACHE_TTL,
        walk_speed_kmh: float = DEFAULT_WALK_SPEED,
        max_walk_km: float = DEFAULT_MAX_WALK_KM,
        history_file: str = "parking_history.csv",
    ):
        self.cache_ttl      = cache_ttl
        self.walk_speed_kmh = walk_speed_kmh
        self.max_walk_km    = max_walk_km
        self.history_file   = history_file

        self._parkings: list[dict] = []
        self._cache_ts: float = 0.0
        self._best_cache: dict[str, Optional[dict]] = {}

        # Dernières valeurs connues par parking_id
        self._last_known: dict[str, dict] = {}

        # Statistiques historiques
        self._slot_mean_nb_libre: dict[tuple[str, str, int], float] = {}
        self._parking_mean_nb_total: dict[str, float] = {}
        self._parking_mean_nb_libre: dict[str, float] = {}
        self._dist_scaler: Optional[RobustScaler] = None
        self._init_dist_scaler()

    # ──────────────────────────────────────────────────────────────────────────
    # SCALING
    # ──────────────────────────────────────────────────────────────────────────

    def _init_dist_scaler(
        self,
        static_path: str = "data/parkings_static.csv",
    ):
        """
        Fitte le RobustScaler sur les distances gare↔parking statiques.
        Appelé une seule fois au __init__.
        """
        try:
            distances = compute_station_parking_distances(static_path)
        except Exception as e:
            return

        arr = distances.reshape(-1, 1)
        self._dist_scaler = RobustScaler()
        self._dist_scaler.fit(arr)


    def scale_dist_parking(self, dist_km: float, max_dist_km: float) -> float:
        """
        Scale une distance gare↔parking avec le RobustScaler statique.

        Parameters
        ----------
        dist_km     : distance temps réel à scaler
        max_dist_km : fallback pour normalisation naïve si scaler absent

        Returns
        -------
        float ∈ [0.0, 1.0]
        """
        if self._dist_scaler is not None:
            scaled = self._dist_scaler.transform([[dist_km]])[0][0]
            return float(np.clip(scaled, 0.0, 1.0))

        # Fallback naïf
        return float(np.clip(dist_km / max_dist_km, 0.0, 1.0))

    # ──────────────────────────────────────────────────────────────────────────
    # API publique
    # ──────────────────────────────────────────────────────────────────────────

    def get_best_parking_for_station(self, station: dict) -> Optional[dict]:
        self._refresh_if_needed()
        if not isinstance(station, dict):
            raise TypeError("station doit être un dict")

        cache_key = station.get("id", f"{station['lat']},{station['lon']}")
        if cache_key not in self._best_cache:
            parking = self.get_nearest_parking(
                lat=station["lat"],
                lon=station["lon"],
            )
            self._best_cache[cache_key] = parking

        return self._best_cache[cache_key]

    def get_walk_time_station_parking(self, station: dict) -> float:
        parking = self.get_best_parking_for_station(station)
        if parking is None:
            return walk_time_min(self.max_walk_km, self.walk_speed_kmh)
        return float(parking["walk_min"])

    def get_parking_availability(self, parking: dict) -> tuple[float, int]:

        if parking is None:
            return 0.0, 0
        nb_libre = parking.get("nb_libre") or 0
        nb_total = parking.get("nb_total") or 0
        taux_libre = round(nb_libre / nb_total, 2) if nb_total > 0 else 0.0
        ouvert = 1 if parking.get("ouvert", False) else 0
        return taux_libre, ouvert

    def get_nearest_parking(self, lat: float, lon: float) -> Optional[dict]:
        self._refresh_if_needed()

        if not self._parkings:
            return None

        nearest = min(
            self._parkings,
            key=lambda p: haversine_km(lat, lon, p["lat"], p["lon"])
        )
        dist_km = haversine_km(lat, lon, nearest["lat"], nearest["lon"])
        return {
            **nearest,
            "dist_km": round(dist_km, 3),
            "walk_min": walk_time_min(dist_km, self.walk_speed_kmh),
        }

    def find_stations_closest_to_their_parking(
        self,
        stations: dict,
        top_k: int = 6,
    ) -> list[dict]:
        """
        Retourne les `top_k` gares dont le parking le plus proche est
        le plus près d'elles (distance gare↔parking minimale).

        Parameters
        ----------
        stations : dict  {station_id: {"lat": ..., "lon": ..., ...}}
                   Typiquement self.sim.stations dans CarSimulator.
        top_k    : nombre de gares à retourner (triées par dist_km croissante)

        Returns
        -------
        list de dicts :
            {
                "station_id"  : str,
                "station_lat" : float,
                "station_lon" : float,
                "parking"     : dict  (le parking le plus proche, avec dist_km et walk_min),
            }
        """
        self._refresh_if_needed()

        if not self._parkings:
            return []

        results = []
        for sid, sdata in stations.items():
            s_lat = sdata["lat"]
            s_lon = sdata["lon"]

            nearest = min(
                self._parkings,
                key=lambda p: haversine_km(s_lat, s_lon, p["lat"], p["lon"])
            )
            dist_km = haversine_km(s_lat, s_lon, nearest["lat"], nearest["lon"])

            results.append({
                "station_id":  sid,
                "station_lat": s_lat,
                "station_lon": s_lon,
                "parking": {
                    **nearest,
                    "dist_km": round(dist_km, 3),
                    "walk_min": walk_time_min(dist_km, self.walk_speed_kmh),
                },
            })

        results.sort(key=lambda x: x["parking"]["dist_km"])
        return results[:top_k]

    def refresh(self):
        records = fetch_parkings()
        if not records:
            self._cache_ts = time.time()
            return

        raw_parkings = [p for p in (parse_parking(r) for r in records) if p]

        sanitized_parkings = []
        seen_ids: set[str] = set()
        now = datetime.now()

        for p in raw_parkings:
            clean = self._sanitize_parking(p, now)
            if clean is None:
                continue

            pid = clean.get("parking_id")

            if not pid or not clean.get("nom", "").strip():
                continue
            if clean.get("nb_total")==0:
                continue
            if pid in seen_ids:
                continue

            seen_ids.add(pid)
            sanitized_parkings.append(clean)

        nb_filtrés = len(raw_parkings) - len(sanitized_parkings)
        self._parkings = sanitized_parkings
        self._cache_ts = time.time()
        self._best_cache.clear()

        self._append_history_snapshot(now)
        self._recompute_history_stats()

    def get_all_parkings(self) -> list[dict]:
        self._refresh_if_needed()
        return list(self._parkings)

    def get_candidate_parkings_for_station(self, station: dict, k: int = 2) -> list[dict]:
        if not isinstance(station, dict):
            raise TypeError("get_candidate_parkings_for_station attend un dict")

        all_parkings = self.get_all_parkings()

        if not all_parkings:
            return []

        lat = station["lat"]
        lon = station["lon"]

        parkings_sorted = sorted(
            all_parkings,
            key=lambda p: haversine_km(lat, lon, p["lat"], p["lon"])
        )

        candidates = []
        for p in parkings_sorted[:k]:
            dist_km = haversine_km(lat, lon, p["lat"], p["lon"])
            candidates.append({
                **p,
                "dist_km": round(dist_km, 3),
                "walk_min": walk_time_min(dist_km, self.walk_speed_kmh),
            })

        return candidates

    # ──────────────────────────────────────────────────────────────────────────
    # Interne
    # ──────────────────────────────────────────────────────────────────────────

    def _refresh_if_needed(self):
        if time.time() - self._cache_ts > self.cache_ttl:
            self.refresh()

    def _get_parking_id(self, parking: dict) -> Optional[str]:
        parking_id = parking.get("parking_id")
        if parking_id is None:
            return None
        return str(parking_id)

    def _day_type(self, dt: datetime) -> str:
        return "weekday" if dt.weekday() < 5 else "weekend"

    def _sanitize_parking(self, parking: dict, now: datetime) -> Optional[dict]:
        """
        Nettoie un parking reçu par l'API :
        - rejette si lat/lon absents ou nuls (coordonnées aberrantes)
        - impute nb_total, nb_libre, ouvert via cascade : API → last_known → historique → 0
        - met à jour les dernières valeurs connues
        """
        lat = parking.get("lat")
        lon = parking.get("lon")

        if lat is None or lon is None:
            return None
        if float(lat) == 0.0 and float(lon) == 0.0:
            return None

        parking_id = self._get_parking_id(parking)
        if parking_id is None:
            return None

        last = self._last_known.get(parking_id, {})

        nb_total = parking.get("nb_total")
        if nb_total is None:
            if last.get("nb_total") is not None:
                nb_total = last["nb_total"]
            elif self._parking_mean_nb_total.get(parking_id) is not None:
                nb_total = round(self._parking_mean_nb_total[parking_id])
            else:
                nb_total = 0

        nb_libre = parking.get("nb_libre")
        if nb_libre is None:
            if last.get("nb_libre") is not None:
                nb_libre = last["nb_libre"]
            else:
                key = (parking_id, self._day_type(now), now.hour)
                if self._slot_mean_nb_libre.get(key) is not None:
                    nb_libre = round(self._slot_mean_nb_libre[key])
                elif self._parking_mean_nb_libre.get(parking_id) is not None:
                    nb_libre = round(self._parking_mean_nb_libre[parking_id])
                else:
                    nb_libre = 0

        nb_total = max(0, int(nb_total))
        nb_libre = max(0, int(nb_libre))
        nb_libre = min(nb_libre, nb_total) if nb_total > 0 else 0

        ouvert = parking.get("ouvert")
        if ouvert is None:
            ouvert = last.get("ouvert", False)

        clean = {
            **parking,
            "parking_id": parking_id,
            "nb_total": nb_total,
            "nb_libre": nb_libre,
            "ouvert": bool(ouvert),
        }

        self._last_known[parking_id] = {
            "nb_total": nb_total,
            "nb_libre": nb_libre,
            "ouvert": bool(ouvert),
        }

        return clean

    def _append_history_snapshot(self, now: datetime):
        file_exists = os.path.exists(self.history_file)

        with open(self.history_file, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "parking_id",
                    "timestamp",
                    "nb_libre",
                    "nb_total",
                    "ouvert",
                ]
            )

            if not file_exists:
                writer.writeheader()

            for p in self._parkings:
                writer.writerow({
                    "parking_id": p["parking_id"],
                    "timestamp": now.isoformat(),
                    "nb_libre": p["nb_libre"],
                    "nb_total": p["nb_total"],
                    "ouvert": int(bool(p["ouvert"])),
                })

    def _recompute_history_stats(self):
        if not os.path.exists(self.history_file):
            return

        try:
            df = pd.read_csv(self.history_file)
        except Exception as e:
            print(f"[ParkingServiceRT] Impossible de lire l'historique : {e}")
            return

        if df.empty:
            return

        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        df = df.dropna(subset=["parking_id", "timestamp"])

        if df.empty:
            return

        df["parking_id"] = df["parking_id"].astype(str)
        df["hour_slot"] = df["timestamp"].dt.hour
        df["day_type"] = df["timestamp"].dt.weekday.apply(
            lambda d: "weekday" if d < 5 else "weekend"
        )

        df["nb_libre"] = pd.to_numeric(df["nb_libre"], errors="coerce")
        df["nb_total"] = pd.to_numeric(df["nb_total"], errors="coerce")
        slot_df = df.dropna(subset=["nb_libre"])
        self._slot_mean_nb_libre = (
            slot_df.groupby(["parking_id", "day_type", "hour_slot"])["nb_libre"]
            .mean()
            .to_dict()
        )

        parking_libre_df = df.dropna(subset=["nb_libre"])
        self._parking_mean_nb_libre = (
            parking_libre_df.groupby("parking_id")["nb_libre"]
            .mean()
            .to_dict()
        )

        parking_total_df = df.dropna(subset=["nb_total"])
        self._parking_mean_nb_total = (
            parking_total_df.groupby("parking_id")["nb_total"]
            .mean()
            .to_dict()
        )
if __name__ == "__main__":
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

    from src.gtfs_service import GTFSService

    gtfs = GTFSService()
    stations = gtfs.load_stops()

    ps = ParkingServiceRT()
    ps.refresh()

    results = ps.find_stations_closest_to_their_parking(
        stations=stations,
        top_k=len(stations)
    )

    for r in results:
        station_id = r["station_id"]
        parking = r["parking"]

        station_name = stations[station_id].get("name", station_id)

        print(
            f"{station_name} | "
            f"{station_id} | "
            f"parking={parking.get('nom')} | "
            f"dist={parking.get('dist_km'):.3f} km | "
            f"walk={parking.get('walk_min'):.2f} min"
        )