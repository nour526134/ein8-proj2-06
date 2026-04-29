import pandas as pd
from pathlib import Path

class GTFSService:
    def __init__(self, gtfs_dir="data/gtfs"):
        p = Path(gtfs_dir)
        self.trips = pd.read_csv(p / "trips.csv")
        self.stop_times = pd.read_csv(p / "stop_times.csv")

    def next_trains(self, stop_id: str, at_time: str, limit: int = 10):
        st = self.stop_times[self.stop_times["stop_id"].astype(str) == str(stop_id)].copy()
        st = st[st["departure_time"].astype(str) >= at_time].sort_values("departure_time").head(limit)
        st = st.merge(self.trips[["trip_id", "route_id"]], on="trip_id", how="left")

        return [
            {
                "trip_id": str(r["trip_id"]),
                "route_id": str(r.get("route_id", "")),
                "departure_time": str(r["departure_time"]),
                "arrival_time": str(r["arrival_time"]) if "arrival_time" in r else None,
            }
            for _, r in st.iterrows()
        ]
