import pandas as pd
import numpy as np
from pathlib import Path
from functools import lru_cache
from typing import Optional


class GTFSService:
    """
    Service GTFS pour Bordeaux (données SNCF).

    Méthodes exposées :
        - load_stops()                          -> dict {stop_id: {lat, lon, name}}
        - get_reachable_stations(stop_id)       -> DataFrame des destinations atteignables
        - train_wait_time_from_trips(origin, dest, time_min) -> float (minutes)
        - train_trip_time(origin, dest)         -> float (minutes, médiane)
    """

    # ------------------------------------------------------------------ #
    #  Init & chargement                                                   #
    # ------------------------------------------------------------------ #

    def __init__(self, gtfs_dir: str = "data/gtfs_bordeaux"):
        self.gtfs_dir = Path(gtfs_dir)
        self._stops: Optional[pd.DataFrame] = None
        self._stop_times: Optional[pd.DataFrame] = None
        self._trips: Optional[pd.DataFrame] = None
        self._calendar_dates: Optional[pd.DataFrame] = None
        self._routes: Optional[pd.DataFrame] = None

        self._load_all()

    # ------------------------------------------------------------------ #

    def _csv(self, name: str) -> Path:
        """Retourne le chemin vers un fichier CSV (ou .txt) GTFS."""
        for ext in (".csv", ".txt"):
            p = self.gtfs_dir / (name + ext)
            if p.exists():
                return p
        raise FileNotFoundError(f"Fichier GTFS introuvable : {name}[.csv/.txt] dans {self.gtfs_dir}")

    def _load_all(self):
        """Charge tous les fichiers GTFS en mémoire et pré-calcule les index."""

        # --- stops ---
        self._stops = pd.read_csv(self._csv("stops"), dtype=str)
        self._stops["stop_lat"] = self._stops["stop_lat"].astype(float)
        self._stops["stop_lon"] = self._stops["stop_lon"].astype(float)

        # --- stop_times ---
        self._stop_times = pd.read_csv(
            self._csv("stop_times"),
            dtype={"trip_id": str, "stop_id": str, "stop_sequence": int},
        )
        # Normalise departure_time en minutes depuis minuit (gère > 24h GTFS)
        self._stop_times["departure_min"] = self._stop_times["departure_time"].apply(
            self._hhmmss_to_min
        )
        self._stop_times["arrival_min"] = self._stop_times["arrival_time"].apply(
            self._hhmmss_to_min
        )

        # --- trips ---
        self._trips = pd.read_csv(self._csv("trips"), dtype=str)

        # --- calendar_dates (optionnel) ---
        try:
            self._calendar_dates = pd.read_csv(self._csv("calendar_dates"), dtype=str)
        except FileNotFoundError:
            self._calendar_dates = None

        # --- routes ---
        try:
            self._routes = pd.read_csv(self._csv("routes"), dtype=str)
        except FileNotFoundError:
            self._routes = None

        # Index utile : stop_id -> ensemble de trip_ids
        self._stop_to_trips = (
            self._stop_times.groupby("stop_id")["trip_id"]
            .apply(set)
            .to_dict()
        )

    # ------------------------------------------------------------------ #
    #  Utilitaires                                                         #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _hhmmss_to_min(t: str) -> float:
        """
        Convertit "HH:MM:SS" en minutes depuis minuit.
        Accepte les valeurs GTFS > 24h (ex : "25:10:00").
        Retourne NaN si invalide.
        """
        try:
            parts = str(t).strip().split(":")
            h, m, s = int(parts[0]), int(parts[1]), int(parts[2])
            return h * 60 + m + s / 60
        except Exception:
            return float("nan")

    @staticmethod
    def _min_to_hhmmss(minutes: float) -> str:
        total_s = int(round(minutes * 60))
        h = total_s // 3600
        m = (total_s % 3600) // 60
        s = total_s % 60
        return f"{h:02d}:{m:02d}:{s:02d}"

    # ------------------------------------------------------------------ #
    #  load_stops                                                          #
    # ------------------------------------------------------------------ #

    def load_stops(self) -> dict:
        """
        Retourne un dictionnaire :
            { stop_id (str) : {"lat": float, "lon": float, "name": str} }

        Filtre sur les arrêts qui ont au moins un départ dans stop_times
        (évite les arrêts fantômes).
        """
        active_stops = set(self._stop_times["stop_id"].unique())
        result = {}
        for _, row in self._stops.iterrows():
            sid = str(row["stop_id"])
            if sid in active_stops:
                result[sid] = {
                    "lat": float(row["stop_lat"]),
                    "lon": float(row["stop_lon"]),
                    "name": str(row.get("stop_name", sid)),
                }
        return result

    # ------------------------------------------------------------------ #
    #  get_reachable_stations                                              #
    # ------------------------------------------------------------------ #

    def get_reachable_stations(self, origin_stop_id: str) -> pd.DataFrame:
        """
        Retourne un DataFrame des stations atteignables depuis `origin_stop_id`
        (même trip, stop_sequence > celui de l'origine).

        Colonnes :
            destination_station_id, destination_lat, destination_lon, destination_name
        """
        origin_stop_id = str(origin_stop_id)

        # trips qui passent par l'origine
        trip_ids = self._stop_to_trips.get(origin_stop_id, set())
        if not trip_ids:
            return pd.DataFrame()

        # stop_times filtrés sur ces trips
        st = self._stop_times[self._stop_times["trip_id"].isin(trip_ids)].copy()

        # séquence de l'origine dans chaque trip
        origin_seq = (
            st[st["stop_id"] == origin_stop_id]
            .set_index("trip_id")["stop_sequence"]
        )

        # joindre pour ne garder que les arrêts APRÈS l'origine
        st = st.join(origin_seq.rename("origin_seq"), on="trip_id")
        st = st.dropna(subset=["origin_seq"])
        st = st[st["stop_sequence"] > st["origin_seq"]]

        dest_ids = st["stop_id"].unique()
        if len(dest_ids) == 0:
            return pd.DataFrame()

        # joindre avec stops pour lat/lon/name
        stops_sub = self._stops[self._stops["stop_id"].isin(dest_ids)][
            ["stop_id", "stop_lat", "stop_lon", "stop_name"]
        ].copy()
        stops_sub = stops_sub.rename(
            columns={
                "stop_id": "destination_station_id",
                "stop_lat": "destination_lat",
                "stop_lon": "destination_lon",
                "stop_name": "destination_name",
            }
        )
        # Dédoublonner
        stops_sub = stops_sub.drop_duplicates(subset=["destination_station_id"])
        return stops_sub.reset_index(drop=True)

    # ------------------------------------------------------------------ #
    #  train_wait_time_from_trips                                          #
    # ------------------------------------------------------------------ #

    def train_wait_time_from_trips(
        self,
        origin_stop_id: str,
        dest_stop_id: str,
        current_time,
    ) -> float:
        """
        Retourne le temps d'attente (en minutes) avant le prochain train
        qui dessert à la fois `origin_stop_id` et `dest_stop_id`
        (avec dest après origin dans le même trip).

        `current_time` peut être :
            - un float (minutes depuis minuit)
            - une str "HH:MM:SS"

        ⚠️  Si le dernier départ de la journée est déjà passé,
            renvoie le temps jusqu'au MÊME train le lendemain
            (24h * 60 - elapsed + départ_du_train).
            Comportement voulu : si tu rates le train de 14h02 à 14h03,
            tu attends ~23h59, pas le train de 15h00.
        """
        origin_stop_id = str(origin_stop_id)
        dest_stop_id = str(dest_stop_id)

        # Normalise current_time en float minutes
        if isinstance(current_time, str):
            current_min = self._hhmmss_to_min(current_time)
        else:
            current_min = float(current_time)

        # Trips valides : passent par origin ET dest, dest après origin
        trips_origin = self._stop_to_trips.get(origin_stop_id, set())
        trips_dest = self._stop_to_trips.get(dest_stop_id, set())
        common_trips = trips_origin & trips_dest
        if not common_trips:
            return float("inf")

        st = self._stop_times[self._stop_times["trip_id"].isin(common_trips)].copy()

        # Séquences origin et dest par trip
        origin_rows = st[st["stop_id"] == origin_stop_id][
            ["trip_id", "stop_sequence", "departure_min"]
        ].rename(columns={"stop_sequence": "seq_orig", "departure_min": "dep_orig"})

        dest_rows = st[st["stop_id"] == dest_stop_id][
            ["trip_id", "stop_sequence"]
        ].rename(columns={"stop_sequence": "seq_dest"})

        merged = origin_rows.merge(dest_rows, on="trip_id")
        # Garder seulement les trips où dest vient après origin
        valid = merged[merged["seq_dest"] > merged["seq_orig"]].copy()
        if valid.empty:
            return float("inf")

        departures = valid["dep_orig"].dropna().values  # minutes depuis minuit

        # Prochains départs >= current_min (dans la journée courante)
        future = departures[departures >= current_min]

        if len(future) > 0:
            next_dep = float(np.min(future))
            return next_dep - current_min
        else:
            # Tous les trains sont passés → prochain est le plus tôt demain
            next_dep = float(np.min(departures))
            # Attente = temps restant jusqu'à minuit + heure du train demain
            wait = (24 * 60 - current_min) + next_dep
            return wait

    # ------------------------------------------------------------------ #
    #  train_trip_time                                                     #
    # ------------------------------------------------------------------ #

    def train_trip_time(self, origin_stop_id: str, dest_stop_id: str) -> float:
        """
        Retourne la durée médiane (en minutes) du trajet en train
        entre `origin_stop_id` et `dest_stop_id`.

        Utilise arrival_time à destination - departure_time à l'origine.
        Retourne inf si aucun trip trouvé.
        """
        origin_stop_id = str(origin_stop_id)
        dest_stop_id = str(dest_stop_id)

        trips_origin = self._stop_to_trips.get(origin_stop_id, set())
        trips_dest = self._stop_to_trips.get(dest_stop_id, set())
        common_trips = trips_origin & trips_dest
        if not common_trips:
            return float("inf")

        st = self._stop_times[self._stop_times["trip_id"].isin(common_trips)].copy()

        origin_rows = st[st["stop_id"] == origin_stop_id][
            ["trip_id", "stop_sequence", "departure_min"]
        ].rename(columns={"stop_sequence": "seq_orig", "departure_min": "dep_orig"})

        dest_rows = st[st["stop_id"] == dest_stop_id][
            ["trip_id", "stop_sequence", "arrival_min"]
        ].rename(columns={"stop_sequence": "seq_dest", "arrival_min": "arr_dest"})

        merged = origin_rows.merge(dest_rows, on="trip_id")
        valid = merged[merged["seq_dest"] > merged["seq_orig"]].copy()
        if valid.empty:
            return float("inf")

        valid["trip_duration"] = valid["arr_dest"] - valid["dep_orig"]
        # Filtre les durées absurdes (négatives ou > 24h)
        valid = valid[(valid["trip_duration"] > 0) & (valid["trip_duration"] < 1440)]
        if valid.empty:
            return float("inf")

        return float(np.median(valid["trip_duration"].values))