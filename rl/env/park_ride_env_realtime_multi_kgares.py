import numpy as np
import gymnasium as gym
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from rl.simulators.car_simulator import CarSimulator
from src.realtime.transit_realtime_service import TransitRealtimeService
from src.gtfs_service import GTFSService
from parking.parking_servicert import ParkingServiceRT
from rl.env.cfg import Configurator
import time

K_STATIONS = 3   
K_PARKINGS  = 2 

FEATURES_PER_STATION = 9
GLOBAL_FEATURES      = 3
OBS_SIZE = GLOBAL_FEATURES + K_STATIONS * FEATURES_PER_STATION

# Actions :
#   0               → voiture directe
#   1 + k*2         → gare k, parking 1
#   2 + k*2         → gare k, parking 2
# Total = 1 + K_STATIONS * K_PARKINGS
N_ACTIONS = 1 + K_STATIONS * K_PARKINGS


def minutes_to_time_str(minutes: float) -> str:
    total_seconds = int(round(minutes * 60))
    total_seconds = total_seconds % (24 * 3600)
    h = total_seconds // 3600
    m = (total_seconds % 3600) // 60
    s = total_seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


class ParkOrRide(gym.Env):
    """
    Env Park-or-Ride avec K gares candidates et 2 parkings par gare.

    Actions :
        0           → continuer en voiture jusqu'à destination
        1 + k*2     → Park & Ride gare k, parking le plus proche
        2 + k*2     → Park & Ride gare k, deuxième parking

    Exemple pour K_STATIONS=3 :
        0 → voiture
        1 → gare 0, parking 0
        2 → gare 0, parking 1
        3 → gare 1, parking 0
        4 → gare 1, parking 1
        5 → gare 2, parking 0
        6 → gare 2, parking 1
    """

    metadata = {"render_modes": ["human"], "render_fps": 30}

    def __init__(self, env_id: int = 0, k_stations: int = K_STATIONS):
        super().__init__()

        self.k_stations_count = k_stations
        self.n_actions        = 1 + k_stations * K_PARKINGS

        self.sim = CarSimulator()
        self.ts  = TransitRealtimeService()
        self.ts.refresh()
        self.ps  = ParkingServiceRT()
        self.cfg = Configurator()
        self.ps.refresh()

        self.truncated     = False
        self.terminated    = False
        self.reward        = 0.0
        self.current_steps = 0
        self.dest_id       = None
        self.env_id        = env_id
        self.episode_count = 0

        # Liste de dicts par gare : {station, parkings}
        self.candidates: list[dict] = []

        self.current_metrics = {}

        os.makedirs("logs", exist_ok=True)
        self.log_file = f"logs/rewards_env_{env_id}.csv"

        obs_size = GLOBAL_FEATURES + k_stations * FEATURES_PER_STATION
        self.observation_space = gym.spaces.Box(
            low=np.zeros(obs_size, dtype=np.float32),
            high=np.ones(obs_size, dtype=np.float32),
            dtype=np.float32,
        )
        self.action_space = gym.spaces.Discrete(self.n_actions)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _norm(self, value: float, max_value: float) -> float:
        if max_value <= 0:
            return 0.0
        return float(np.clip(value / max_value, 0.0, 1.0))

    def _decode_action(self, action: int):
        """
        Retourne (station_idx, parking_idx) ou None pour l'action voiture.
            action == 0          → None
            action == 1 + k*2    → (k, 0)
            action == 2 + k*2    → (k, 1)
        """
        if action == 0:
            return None
        action -= 1
        station_idx = action // K_PARKINGS
        parking_idx = action % K_PARKINGS
        return station_idx, parking_idx

    def _get_train_times(self, station_id, dest_id, arrival_time_min):
        """Retourne (train_wait, train_trip) avec fallback sur cfg."""
        try:
            train_wait = float(self.ts.train_wait_time_from_trips_realtime(
                station_id, dest_id, arrival_time_min
            ))
            train_trip = float(self.ts.gtfs.train_trip_time(station_id, dest_id))
        except Exception:
            train_wait = float(self.cfg.max_wait_min)
            train_trip = float(self.cfg.max_trip_min)
        return train_wait, train_trip

    def _parking_taux(self, parking) -> float:
        if parking is None:
            return 0.0
        nb_libre = parking.get("nb_libre") or 0
        nb_total = parking.get("nb_total") or 0
        return round(nb_libre / nb_total, 2) if nb_total > 0 else 0.0

    # ── Observation ───────────────────────────────────────────────────────────

    def _get_observation(self) -> np.ndarray:
        metrics = self.sim.get_metrics() or {}
        self.current_metrics = metrics

        dist_dest    = metrics.get("dist_to_dest_km", 0.0)
        traffic      = metrics.get("traffic", 0.0)
        eta_car_dest = float(self.sim.car_time_to_dest())
        time_min     = metrics.get("time_min", 0.0)

        # Features globales
        obs = [
            self._norm(dist_dest,    self.cfg.max_dist_dest_km),
            float(np.clip(traffic,   0.0, 1.0)),
            self._norm(eta_car_dest, self.cfg.max_eta_min),
        ]
        for cand in self.candidates:
            station    = cand["station"]
            parkings   = cand["parkings"]   # liste de 0, 1 ou 2 dicts parking
            station_id = station["id"]

            dist_station = cand.get("dist_station_km", 0.0)

            # Parking 0
            p0 = parkings[0] if len(parkings) > 0 else None
            dist_p0     = float(p0["dist_km"])               if p0 else self.cfg.max_dist_parking_km
            eta_p0      = float(self.sim.car_time_to_parking(p0)) if p0 else self.cfg.max_eta_min
            taux_p0     = self._parking_taux(p0)

            # Parking 1
            p1 = parkings[1] if len(parkings) > 1 else None
            dist_p1     = float(p1["dist_km"])               if p1 else self.cfg.max_dist_parking_km
            eta_p1      = float(self.sim.car_time_to_parking(p1)) if p1 else self.cfg.max_eta_min
            taux_p1     = self._parking_taux(p1)

            # Train depuis gare k avec parking 0 comme référence d'arrivée à la gare
            arrival_ref = time_min + eta_p0 + (float(p0["walk_min"]) if p0 else 0.0)
            if station_id is not None and self.dest_id is not None:
                train_wait, train_trip = self._get_train_times(station_id, self.dest_id, arrival_ref)
            else:
                train_wait = float(self.cfg.max_wait_min)
                train_trip = float(self.cfg.max_trip_min)

            obs += [
                self._norm(dist_station, self.cfg.max_dist_station_km),
                self._norm(dist_p0,      self.cfg.max_dist_parking_km),
                self._norm(eta_p0,       self.cfg.max_eta_min),
                float(np.clip(taux_p0,   0.0, 1.0)),
                self._norm(dist_p1,      self.cfg.max_dist_parking_km),
                self._norm(eta_p1,       self.cfg.max_eta_min),
                float(np.clip(taux_p1,   0.0, 1.0)),
                self._norm(train_wait,   self.cfg.max_wait_min),
                self._norm(train_trip,   self.cfg.max_trip_min),
            ]

        # Padding si on a moins de k_stations_count gares valides
        missing = self.k_stations_count - len(self.candidates)
        for _ in range(missing):
            obs += [1.0] * FEATURES_PER_STATION  # valeurs max = pénalisant

        return np.array(obs, dtype=np.float32)

    # ── Reset ─────────────────────────────────────────────────────────────────

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)

        # Reset simulateur avec k gares candidates
        self.sim.reset(seed=seed, k_stations=self.k_stations_count)

        self.dest_id       = self.sim.get_dest_id()
        self.truncated     = False
        self.terminated    = False
        self.reward        = 0.0
        self.current_steps = 0
        self.candidates    = []
        self.current_metrics = {}
        self.episode_count += 1

        for _ in range(self.cfg.max_iterations):
            self.current_steps += 1
            self.sim.advance(self.cfg.dt_min)

            # On décide au voisinage de la gare la plus proche (gare 0)
            dist_station_0 = float(self.sim.get_dist_to_station_km())
            if dist_station_0 <= self.cfg.decision_distance_km:

                k_stations_data = self.sim.get_k_stations()  # liste triée par dist_km
                if len(k_stations_data) < 1:
                    continue

                # Construire la liste candidates
                self.candidates = []
                valid = True

                for ks in k_stations_data[: self.k_stations_count]:
                    station_dict = {
                        "id":  ks["id"],
                        "lat": ks["lat"],
                        "lon": ks["lon"],
                    }
                    parkings = self.ps.get_candidate_parkings_for_station(station_dict, k=K_PARKINGS)

                    # On exige au moins 1 parking par gare pour que ce soit utile
                    if len(parkings) == 0:
                        valid = False
                        break

                    self.candidates.append({
                        "station":          station_dict,
                        "parkings":         parkings,
                        "dist_station_km":  ks["dist_km"],
                    })

                if not valid or len(self.candidates) == 0:
                    self.candidates = []
                    continue

                obs  = self._get_observation()
                info = {
                    "reset":       "success",
                    "n_stations":  len(self.candidates),
                    "station_ids": [c["station"]["id"] for c in self.candidates],
                    "dest_id":     self.dest_id,
                }
                return obs, info

        self.truncated = True
        obs  = self._get_observation()
        info = {"reset": "truncated_before_decision"}
        return obs, info

    # ── Step ──────────────────────────────────────────────────────────────────

    def step(self, action: int):
        if not self.action_space.contains(action):
            raise ValueError(f"Invalid action: {action}")

        if self.truncated or self.terminated:
            obs = self._get_observation()
            return obs, 0.0, True, True, {"state": "already_ended"}

        lambda_parking = 0.1
        current_time   = float(self.sim.get_time_min())
        car_dest_time  = float(self.sim.car_time_to_dest())

        decoded = self._decode_action(action)

        # ── Action 0 : voiture directe ────────────────────────────────────────
        if decoded is None:
            # Calcul du meilleur temps possible (toutes options)
            best_transit_time = self._best_transit_time(current_time)
            best_time = min(car_dest_time, best_transit_time)
            reward_temps = (best_time - car_dest_time) / max(best_time, car_dest_time, 1.0)

            self.reward = float(reward_temps)
            mode = "car_direct"
            total_time = car_dest_time
            info_parking_id   = None
            info_parking_name = None
            info_station_id   = None
            taux_parking      = 0.0
            parking_penalty   = 0.0
            car_parking_time  = 0.0
            walk_time         = 0.0
            train_wait        = 0.0
            train_trip        = 0.0
            time_transit      = float("inf")

        # ── Actions 1+ : Park & Ride ──────────────────────────────────────────
        else:
            station_idx, parking_idx = decoded

            # Gare et parking choisis (avec fallback si hors limites)
            if station_idx >= len(self.candidates):
                station_idx = len(self.candidates) - 1
            cand    = self.candidates[station_idx]
            station = cand["station"]
            parkings = cand["parkings"]

            if parking_idx >= len(parkings):
                parking_idx = len(parkings) - 1
            selected_parking = parkings[parking_idx]

            info_station_id   = station["id"]
            info_parking_id   = selected_parking.get("parking_id")
            info_parking_name = selected_parking.get("nom")

            car_parking_time = float(self.sim.car_time_to_parking(selected_parking))
            walk_time        = float(selected_parking["walk_min"])
            taux_parking     = self._parking_taux(selected_parking)

            arrival_at_station = current_time + car_parking_time + walk_time
            train_wait, train_trip = self._get_train_times(
                info_station_id, self.dest_id, arrival_at_station
            )

            time_transit = car_parking_time + walk_time + train_wait + train_trip

            # Meilleur temps global
            best_transit_time = self._best_transit_time(current_time)
            best_time = min(car_dest_time, best_transit_time)
            # Si pas de train trouvé → reward très négatif 
            if time_transit == float("inf"):
                reward_temps = -1.0
                parking_penalty = 0.0
            else:
                reward_temps = (best_time - time_transit) / max(best_time, time_transit, 1.0)
                parking_penalty = lambda_parking * (1.0 - taux_parking)
            self.reward = float(reward_temps - parking_penalty)
            mode        = f"park_station{station_idx}_p{parking_idx}"
            total_time  = time_transit

        with open(self.log_file, "a") as f:
            f.write(f"{self.episode_count},{self.reward},{time.time()}\n")

        self.terminated = True
        self.truncated  = False

        info = {
            "action":             int(action),
            "mode":               mode,
            "station_id":         info_station_id ,
            "parking_id":         info_parking_id ,
            "parking_name":       info_parking_name ,
            "time_min_decision":  current_time,
            "car_dest_time":      car_dest_time,
            "car_parking_time":   car_parking_time ,
            "walk_time":          walk_time       ,
            "train_wait_min":     train_wait      ,
            "train_trip_min":     train_trip      ,
            "time_car":           car_dest_time,
            "time_transit":       time_transit    ,
            "taux_parking":       taux_parking,
            "reward_temps":       float(reward_temps),
            "parking_penalty":    float(parking_penalty) ,
            "total_time_min":     float(total_time),
            "reward":             float(self.reward),
            "done_reason":        "decision_made",
        }

        obs = self._get_observation()
        return obs, float(self.reward), self.terminated, self.truncated, info

    # ── Interne ───────────────────────────────────────────────────────────────

    def _best_transit_time(self, current_time: float) -> float:
        """Calcule le meilleur temps transit possible parmi tous les candidats."""
        best = float("inf")
        for cand in self.candidates:
            station_id = cand["station"]["id"]
            for p in cand["parkings"]:
                eta_p      = float(self.sim.car_time_to_parking(p))
                walk        = float(p["walk_min"])
                arr         = current_time + eta_p + walk
                wait, trip  = self._get_train_times(station_id, self.dest_id, arr)
                t           = eta_p + walk + wait + trip
                if t < best:
                    best = t
        return best

    # ── Render ────────────────────────────────────────────────────────────────

    def render(self, mode="human"):
        if mode != "human":
            return
        m = self.current_metrics or {}
        print(
            f"Step={self.current_steps} | "
            f"Terminated={self.terminated} | Truncated={self.truncated} | "
            f"Reward={self.reward:.3f} | "
            f"N_stations={len(self.candidates)} | "
            f"Dest={self.dest_id} | "
            f"Time={m.get('time_min', 0.0):.1f} min | "
            f"Dist_dest={m.get('dist_to_dest_km', 0.0):.2f} km | "
            f"Traffic={m.get('traffic', 0.0):.2f}"
        )


# ── Main test ─────────────────────────────────────────────────────────────────

def main():
    env = ParkOrRide(k_stations=3)

    print("=== RESET ===")
    obs, info = env.reset()
    print("Obs shape :", obs.shape)
    print("Info      :", info)

    action = env.action_space.sample()
    labels = {0: "voiture"}
    for k in range(env.k_stations_count):
        labels[1 + k * 2] = f"gare {k}, parking 0"
        labels[2 + k * 2] = f"gare {k}, parking 1"

    print(f"\nAction choisie : {action} → {labels.get(action, '?')}")
    obs, reward, terminated, truncated, info = env.step(action)
    print("Reward :", reward)
    print("Info   :", info)
    env.render()


if __name__ == "__main__":
    main()