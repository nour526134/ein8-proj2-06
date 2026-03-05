import pandas as pd
from pathlib import Path


class TrainService:
    """
    Service train simple pour l'évaluation.
    Lit les données GTFS et fournit les horaires.
    """

    def __init__(self, gtfs_dir="data/gtfs"):
        p = Path(gtfs_dir)
        try:
            self.trips = pd.read_csv(p / "trips.txt")
            self.stop_times = pd.read_csv(p / "stop_times.txt")
            self.stops = pd.read_csv(p / "stops.txt")
            self._loaded = True
        except FileNotFoundError:
            self._loaded = False

    def get_next_train_wait(self, stop_id: str, current_time_min: float) -> float:
        """
        Retourne le temps d'attente en minutes jusqu'au prochain train.
        current_time_min : temps actuel en minutes depuis minuit
        """
        if not self._loaded:
            # Fallback simulé si pas de données GTFS
            import random
            return random.uniform(2.0, 25.0)

        # Convertir minutes → HH:MM:SS
        h = int(current_time_min // 60)
        m = int(current_time_min % 60)
        at_time = f"{h:02d}:{m:02d}:00"

        st = self.stop_times[
            self.stop_times["stop_id"].astype(str) == str(stop_id)
        ].copy()

        st = st[
            st["departure_time"].astype(str) >= at_time
        ].sort_values("departure_time")

        if len(st) == 0:
            return 20.0  # valeur par défaut si aucun train

        # Prendre le premier train
        next_departure = st.iloc[0]["departure_time"]

        # Convertir HH:MM:SS → minutes
        parts = str(next_departure).split(":")
        next_min = int(parts[0]) * 60 + int(parts[1])

        wait = next_min - current_time_min
        return max(0.0, float(wait))

    def get_train_travel_time(self, origin_stop_id: str, dest_stop_id: str) -> float:
        """
        Retourne le temps de trajet en train entre deux gares en minutes.
        Version simplifiée : retourne une valeur simulée.
        """
        import random
        return random.uniform(15.0, 60.0)

    def get_train_delay(self) -> float:
        """
        Retourne un retard simulé en minutes.
        """
        import random
        return random.uniform(0.0, 10.0)
