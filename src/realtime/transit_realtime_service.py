from pathlib import Path
from typing import Dict, Any, Optional
import requests
import numpy as np
import sys
from google.transit import gtfs_realtime_pb2
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from src.gtfs_service import GTFSService


class TransitRealtimeService:
    """Service  qui télécharge le flux GTFS-RT Trip Updates SNCF et stocke les mises à jour par trip_id"""
    def __init__(
        self,
        trip_updates_url= "https://proxy.transport.data.gouv.fr/resource/sncf-gtfs-rt-trip-updates",
        timeout: int = 20
    ):
        
        self.gtfs = GTFSService()
        self.trip_updates_url = trip_updates_url
        self.timeout = timeout
        self.trip_updates: Dict[str, Dict[str, Any]] = {}


    def refresh(self) -> None:
        """Télécharge le flux GTFS-RT et met à jour self.trip_updates."""
        response = requests.get(self.trip_updates_url, timeout=self.timeout)
        response.raise_for_status() # verifie si reponse est correcte( code 200 si tout va bien)
        feed = gtfs_realtime_pb2.FeedMessage() #creer un objet gtfs-rt vide
        feed.ParseFromString(response.content)
        updates: Dict[str, Dict[str, Any]] = {}

        for entity in feed.entity:
            
            if not entity.HasField("trip_update"):
                continue
            trip_update = entity.trip_update # cela contient 3 champs tres important trip , vehicule et stop_time_update
            trip_descriptor = trip_update.trip
            trip_id = trip_descriptor.trip_id.strip() if trip_descriptor.trip_id else None

            if not trip_id:
                continue
            delay_sec: Optional[int ] = None
            # On essaie de récupérer un delay depuis les stop_time_updates
            stop_updates = []

            for stu in trip_update.stop_time_update:
                arr_delay = stu.arrival.delay if stu.HasField("arrival") and stu.arrival.HasField("delay") else None
                dep_delay = stu.departure.delay if stu.HasField("departure") and stu.departure.HasField("delay") else None

                if delay_sec is None:
                    if dep_delay is not None:
                        delay_sec = dep_delay
                    elif arr_delay is not None:
                        delay_sec = arr_delay
                stop_updates.append(
                    {
                        "stop_id": stu.stop_id,
                        "stop_sequence": stu.stop_sequence,
                        "arrival_delay_sec": arr_delay,
                        "departure_delay_sec": dep_delay,
                    }
                )
            if delay_sec is None:
                delay_sec = 0

            schedule_relationship = trip_descriptor.schedule_relationship
            cancelled = schedule_relationship == gtfs_realtime_pb2.TripDescriptor.CANCELED

            vehicle_id = ""
            if trip_update.HasField("vehicle") and trip_update.vehicle.id:
                vehicle_id = trip_update.vehicle.id

            updates[trip_id] = {
                "delay_min": float(delay_sec) / 60.0,
                "cancelled": cancelled,
                "vehicle_id": vehicle_id,
                "stop_time_updates": stop_updates,
            }

        self.trip_updates = updates


    def get_trip_update(self, trip_id: str) -> Optional[Dict[str, Any]]:
        """Retourne tout l'objet update d'un trip, ou None si absent """
        return self.trip_updates.get(str(trip_id))


    def get_trip_delay(self, trip_id: str) -> float:
        """
        Retourne le retard en minutes d'un trip.
        Si aucune info temps réel n'existe, retourne 0.0
        """
        update = self.get_trip_update(trip_id)
        if update is None:
            return 0.0
        return float(update.get("delay_min", 0.0))


    def is_trip_cancelled(self, trip_id: str) -> bool:
        """Retourne True si le trip est annoncé annulé dans le flux temps réel."""
        update = self.get_trip_update(trip_id)
        if update is None:
            return False
        return bool(update.get("cancelled", False))


    def print_trips(self, n: int = 5) -> None:
        """ afficher ce qui a été chargé"""
        for i, (trip_id, data) in enumerate(self.trip_updates.items()):
            if i >= n:
                break
            print(
                f"trip_id={trip_id} | "
                f"delay_min={data['delay_min']:.2f} | "
                f"cancelled={data['cancelled']} | "
                f"vehicle_id={data['vehicle_id']}"
            )



    def train_wait_time_from_trips_realtime(
        self,
        origin_stop_id,
        dest_stop_id,
        current_time,
    ) -> float:
        """Retourne le temps d'attente réel (en minutes) avant le prochain train allant de origin_stop_id à dest_stop_id, en tenant compte :du GTFS statique ,des annulations temps réel et des retards temps réel"""
        origin_stop_id = str(origin_stop_id)
        dest_stop_id = str(dest_stop_id)

        # convertir en min 
        if isinstance(current_time, str):
            current_min = self.gtfs._hhmmss_to_min(current_time)
        else:
            current_min = float(current_time)

        # Trips qui passent par orig et dest
        trips_origin = self.gtfs._stop_to_trips.get(origin_stop_id, set())
        trips_dest = self.gtfs._stop_to_trips.get(dest_stop_id, set())
        common_trips = trips_origin & trips_dest
        if not common_trips:
            return float("inf")

        # Sous-table stop_times pour ces trips
        st = self.gtfs._stop_times[self.gtfs._stop_times["trip_id"].isin(common_trips)].copy()

        # Infos à l'origine
        origin_rows = st[st["stop_id"] == origin_stop_id][
            ["trip_id", "stop_sequence", "departure_min"]
        ].rename(columns={"stop_sequence": "seq_orig", "departure_min": "dep_orig"})

        # Infos à la destination
        dest_rows = st[st["stop_id"] == dest_stop_id][
            ["trip_id", "stop_sequence"]
        ].rename(columns={"stop_sequence": "seq_dest"})

        merged = origin_rows.merge(dest_rows, on="trip_id")

        # On garde seulement les trips où la destination est après l'origine
        valid = merged[merged["seq_dest"] > merged["seq_orig"]].copy()

        if valid.empty:
            return float("inf")

        real_departures = []

        for _, row in valid.iterrows():
            trip_id = str(row["trip_id"])

            # Ignorer les trips annulés
            if self.is_trip_cancelled(trip_id):
                continue

            dep_orig = float(row["dep_orig"])
            delay_min = self.get_trip_delay(trip_id)

            dep_real = dep_orig + delay_min
            real_departures.append(dep_real)

        if not real_departures:
            return float("inf")

        real_departures = np.array(real_departures, dtype=float)

        future = real_departures[real_departures >= current_min]

        if len(future) > 0:
            next_dep = float(np.min(future))
            return next_dep - current_min
        else:
            next_dep = float(np.min(real_departures))
            return (24 * 60 - current_min) + next_dep
    def find_best_destination_by_wait(
        self,
        origin_id: str,
        current_time_min: float
    ):
        """
        Trouve, parmi les stations atteignables depuis origin_id,
        la destination avec le plus petit temps total réel = attente + trajet train.
        """
 
        origin_id = str(origin_id)
 
        reachable_stations = self.gtfs.get_reachable_stations(origin_id)
 
        if reachable_stations.empty:
            print(origin_id)
            print("REACHABE")
            return None
 
        best_dest = None
        best_total = float("inf")
        best_wait = float("inf")
        best_trip = float("inf")
        best_name = None
 
        for _, row in reachable_stations.iterrows():
            dest_id = str(row["destination_station_id"])
 
            if dest_id == origin_id:
                continue
 
            wait = self.train_wait_time_from_trips_realtime(
                origin_id,
                dest_id,
                current_time_min
            )

            if not np.isfinite(wait) or wait < 0:
                continue
 
            try:
                trip = float(self.gtfs.train_trip_time(origin_id, dest_id))
            except Exception:
                continue
 
            if not np.isfinite(trip) or trip <= 0:
                continue
 
            total = wait + trip
 
            if total < best_total:
                best_total = total
                best_wait = wait
                best_trip = trip
                best_dest = dest_id
                best_name = row.get("destination_name", None)
 
        if best_dest is None:
            return None
 
        return {
            "origin": origin_id,
            "destination": best_dest,
            "destination_name": best_name,
            "wait_min": round(best_wait, 2),
            "trip_min": round(best_trip, 2),
            "total_min": round(best_total, 2),
        }
def debug_wait_candidates(service, origin_stop_id, dest_stop_id, current_time, limit=10):
    origin_stop_id = str(origin_stop_id)
    dest_stop_id = str(dest_stop_id)

    if isinstance(current_time, str):
        current_min = service.gtfs._hhmmss_to_min(current_time)
    else:
        current_min = float(current_time)

    print("=" * 80)
    print(f"DEBUG WAIT")
    print(f"origin      = {origin_stop_id}")
    print(f"destination = {dest_stop_id}")
    print(f"current_time= {current_time} ({current_min:.2f} min)")
    print("=" * 80)

    trips_origin = service.gtfs._stop_to_trips.get(origin_stop_id, set())
    trips_dest = service.gtfs._stop_to_trips.get(dest_stop_id, set())
    common_trips = trips_origin & trips_dest

    print(f"Trips origin : {len(trips_origin)}")
    print(f"Trips dest   : {len(trips_dest)}")
    print(f"Common trips : {len(common_trips)}")

    if not common_trips:
        print("Aucun trip commun.")
        return

    st = service.gtfs._stop_times[
        service.gtfs._stop_times["trip_id"].isin(common_trips)
    ].copy()

    origin_rows = st[st["stop_id"] == origin_stop_id][
        ["trip_id", "stop_sequence", "departure_min", "departure_time"]
    ].rename(columns={
        "stop_sequence": "seq_orig",
        "departure_min": "dep_orig_min",
        "departure_time": "dep_orig_str",
    })

    dest_rows = st[st["stop_id"] == dest_stop_id][
        ["trip_id", "stop_sequence", "arrival_min", "arrival_time"]
    ].rename(columns={
        "stop_sequence": "seq_dest",
        "arrival_min": "arr_dest_min",
        "arrival_time": "arr_dest_str",
    })

    merged = origin_rows.merge(dest_rows, on="trip_id")
    valid = merged[merged["seq_dest"] > merged["seq_orig"]].copy()

    if valid.empty:
        print("Aucun trip valide avec destination après origine.")
        return

    rows = []

    for _, row in valid.iterrows():
        trip_id = str(row["trip_id"])
        dep_orig = float(row["dep_orig_min"])
        arr_dest = float(row["arr_dest_min"])
        trip_time = arr_dest - dep_orig

        rt = service.get_trip_update(trip_id)
        cancelled = service.is_trip_cancelled(trip_id)
        delay_min = service.get_trip_delay(trip_id)

        dep_real = dep_orig + delay_min

        rows.append({
            "trip_id": trip_id,
            "dep_theoretical": row["dep_orig_str"],
            "arr_theoretical": row["arr_dest_str"],
            "dep_orig_min": dep_orig,
            "arr_dest_min": arr_dest,
            "trip_time_min": trip_time,
            "delay_min": delay_min,
            "dep_real_min": dep_real,
            "wait_real_min": dep_real - current_min,
            "cancelled": cancelled,
            "has_rt": rt is not None,
        })

    rows = sorted(rows, key=lambda x: x["dep_real_min"])

    print("\n--- TOUS LES CANDIDATS (triés par départ réel) ---")
    for r in rows[:limit]:
        print(
            f"trip_id={r['trip_id']} | "
            f"dep_th={r['dep_theoretical']} | "
            f"arr_th={r['arr_theoretical']} | "
            f"trip={r['trip_time_min']:.1f} min | "
            f"delay={r['delay_min']:.1f} min | "
            f"dep_real={r['dep_real_min']:.1f} | "
            f"wait_real={r['wait_real_min']:.1f} | "
            f"cancelled={r['cancelled']} | "
            f"has_rt={r['has_rt']}"
        )

    static_wait = service.gtfs.train_wait_time_from_trips(
        origin_stop_id, dest_stop_id, current_min
    )
    realtime_wait = service.train_wait_time_from_trips_realtime(
        origin_stop_id, dest_stop_id, current_min
    )
    static_trip = service.gtfs.train_trip_time(origin_stop_id, dest_stop_id)

    print("\n--- RÉSULTATS FONCTIONS ---")
    print(f"train_wait_time_from_trips          = {static_wait:.2f} min")
    print(f"train_wait_time_from_trips_realtime = {realtime_wait:.2f} min")
    print(f"train_trip_time                     = {static_trip:.2f} min")
    print("=" * 80)



if __name__ == "__main__":
    service = TransitRealtimeService()
    service.refresh()
    stops = service.gtfs.load_stops()

    ids = [
        "StopPoint:OCETrain TER-87581850",
        "StopPoint:OCETrain TER-87581751",
    ]

    print(stops[stops["stop_id"].isin(ids)][["stop_id", "stop_name"]])
        