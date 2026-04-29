import numpy as np
import gymnasium as gym
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

#from simu.car_simulator import CarSimulator
from rl.simulators.car_simulator import CarSimulator
from src.realtime.transit_realtime_service import TransitRealtimeService
from src.gtfs_service import GTFSService
from parking.parking_servicert import ParkingServiceRT
from rl.env.cfg import Configurator
import time


# Observation (taille 9) :
# [dist_dest, dist_station, dist_parking,
#  traffic,
#  eta_car_dest, eta_car_parking,
#  train_wait, train_trip,
#  taux_parking]

OBS_SIZE = 12


def minutes_to_time_str(minutes: float) -> str:
    total_seconds = int(round(minutes * 60))
    total_seconds = total_seconds % (24 * 3600)
    h = total_seconds // 3600
    m = (total_seconds % 3600) // 60
    s = total_seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


class ParkOrRideMulti(gym.Env):
    """
    Gym Environment for Park-or-Ride (1 gare, 2 parking candidats).

    Actions:
        0 → continuer en voiture jusqu'à destination
        1 → Park & Ride (garer au parking, marcher, prendre le train)
        2 → Park & Ride avec le deuxième parking candidat

    Observation (taille 9) :
        dist_dest       : distance voiture → destination      (normalisée)
        dist_station    : distance voiture → gare             (normalisée)
        dist_parking    : distance voiture → parking          (normalisée)
        traffic         : indice trafic                       (0-1)
        eta_car_dest    : temps voiture → destination         (normalisé)
        eta_car_parking : temps voiture → parking             (normalisé)
        train_wait      : attente prochain train              (normalisé)
        train_trip      : durée trajet train                  (normalisé)
        taux_parking    : taux de places libres               (0-1)

    Reward ratio :
        reward = (time_car - time_train) / max(time_car, time_train)
        ∈ [-1, +1], positif si le choix effectué était le meilleur.
    """

    metadata = {"render_modes": ["human"], "render_fps": 30}

    def __init__(self,env_id=0):
        super().__init__()

        self.sim     = CarSimulator()
        self.ts      = TransitRealtimeService()
        self.ts.refresh()
        self.ps      = ParkingServiceRT()
        self.cfg     = Configurator()
        self.ps.refresh()
        self.truncated       = False
        self.terminated      = False
        self.reward          = 0.0
        self.current_steps   = 0
        self.dest_id         = None
        self.station         = None   # dict {id, lat, lon}
        self.station_id      = None
        self.parkings = []
        self.parking         = None   # dict parking ou None
        self.current_metrics = {}
        self.env_id=env_id
        self.episode_count = 0
        os.makedirs("logs", exist_ok=True)
        self.log_file = f"logs/rewards_env_{env_id}.csv"
        self.observation_space = gym.spaces.Box(
            low=np.zeros(OBS_SIZE, dtype=np.float32),
            high=np.ones(OBS_SIZE, dtype=np.float32),
            dtype=np.float32,
        )
        self.action_space = gym.spaces.Discrete(3)  # 0=voiture, 1=train 3=train +2eme parking plus proche

    # ── Normalisation ─────────────────────────────────────────────────────────

    def _norm(self, value: float, max_value: float) -> float:
        if max_value <= 0:
            return 0.0
        return float(np.clip(value / max_value, 0.0, 1.0))

    # ── Observation ───────────────────────────────────────────────────────────

    def _get_observation(self) -> np.ndarray:
        metrics = self.sim.get_metrics() or {}
        self.current_metrics = metrics

        dist_dest    = metrics.get("dist_to_dest_km",    0.0)
        dist_station = metrics.get("dist_to_station_km", 0.0)
        if self.parking is not None:
            dist_parking = float(self.parking.get("dist_km", 0.0))
        else:
            dist_parking = 0.0
        traffic      = metrics.get("traffic",            0.0)
        time_min     = metrics.get("time_min",           0.0)
        eta_car_dest    = float(self.sim.car_time_to_dest())
        if(self.parking):
            eta_car_parking = float(self.sim.car_time_to_parking(self.parking))
        else:
            eta_car_parking=np.inf

        if self.station_id is None:
            train_wait = float(self.cfg.max_wait_min)
            train_trip = float(self.cfg.max_trip_min)
        else:
            try:
                train_wait = float(self.ts.train_wait_time_from_trips_realtime(
                    self.station_id, self.dest_id, time_min
                ))
                train_trip = float(self.ts.gtfs.train_trip_time(
                    self.station_id, self.dest_id
                ))
            except Exception:
                train_wait = float(self.cfg.max_wait_min)
                train_trip = float(self.cfg.max_trip_min)

        # Disponibilité parking
        if self.parking is not None:
            nb_libre = self.parking.get("nb_libre") or 0
            nb_total = self.parking.get("nb_total") or 0
            taux_parking = round(nb_libre / nb_total, 2) if nb_total > 0 else 0.0
        else:
            taux_parking = 0.0

        # Parking 2
        parking_2 = self.parkings[1] if len(self.parkings) > 1 else None

        if parking_2 is not None:
            dist_parking_2 = float(parking_2.get("dist_km", 0.0))
            eta_car_parking_2 = float(self.sim.car_time_to_parking(parking_2))
            nb_libre_2 = parking_2.get("nb_libre") or 0
            nb_total_2 = parking_2.get("nb_total") or 0
            taux_parking_2 = round(nb_libre_2 / nb_total_2, 2) if nb_total_2 > 0 else 0.0
        else:
            dist_parking_2 = self.cfg.max_dist_parking_km
            eta_car_parking_2 = self.cfg.max_eta_min
            taux_parking_2 = 0.0

        obs = np.array([
            self._norm(dist_dest,       self.cfg.max_dist_dest_km),
            self._norm(dist_station,    self.cfg.max_dist_station_km),
            self._norm(dist_parking,    self.cfg.max_dist_parking_km),
            float(np.clip(traffic,      0.0, 1.0)),
            self._norm(eta_car_dest,    self.cfg.max_eta_min),
            self._norm(eta_car_parking, self.cfg.max_eta_min),
            self._norm(train_wait,      self.cfg.max_wait_min),
            self._norm(train_trip,      self.cfg.max_trip_min),
            float(np.clip(taux_parking, 0.0, 1.0)),
    
            self._norm(dist_parking_2,    self.cfg.max_dist_parking_km),
            self._norm(eta_car_parking_2, self.cfg.max_eta_min),
            float(np.clip(taux_parking_2, 0.0, 1.0)),
        ], dtype=np.float32)

        return obs

    # ── Reset ─────────────────────────────────────────────────────────────────

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)

        self.sim.reset(seed=seed)
        self.dest_id         = self.sim.get_dest_id()
        self.truncated       = False
        self.terminated      = False
        self.reward          = 0.0
        self.current_steps   = 0
        self.station         = None
        self.station_id      = None
        self.parkings = []
        self.parking         = None
        self.current_metrics = {}
        self.episode_count += 1

        for _ in range(self.cfg.max_iterations):
            self.current_steps += 1
            self.sim.advance(self.cfg.dt_min)

            dist_station = float(self.sim.get_dist_to_station_km())
            if dist_station <= self.cfg.decision_distance_km:

                start_station   = self.sim.get_closest_station()
                self.station_id = start_station["id"]
                self.station    = {
                    "id":  start_station["id"],
                    "lat": start_station["lat"],
                    "lon": start_station["lon"],
                }
                self.parkings = self.ps.get_candidate_parkings_for_station(self.station, k=2)
                if len(self.parkings) < 2:
                    continue
                self.parking = self.parkings[0] if len(self.parkings) > 0 else None
                obs  = self._get_observation()
                info = {
                    "reset":      "success",
                    "station_id": self.station_id,
                    "dest_id":    self.dest_id,
                    "parking_id": self.parking["parking_id"] if self.parking else None,
                }
                return obs, info

        # Pas arrivé au point de décision
        self.truncated = True
        obs  = self._get_observation()
        info = {"reset": "truncated_before_decision"}
        return obs, info

    # ── Step ──────────────────────────────────────────────────────────────────

    def step(self, action):
        if not self.action_space.contains(action):
            raise ValueError(f"Invalid action: {action}")

        if self.truncated or self.terminated:
            obs = self._get_observation()
            return obs, 0.0, True, True, {"state": "already_ended"}

        lambda_parking = 0.1  # à ajuster (ex: 0.1 à 0.3)

        current_time = float(self.sim.get_time_min())
        car_dest_time = float(self.sim.car_time_to_dest())

        selected_parking = None
        if int(action) == 1:
            if len(self.parkings) > 0:
                selected_parking = self.parkings[0]

        elif int(action) == 2:
            if len(self.parkings) > 1:
                selected_parking = self.parkings[1]
            elif len(self.parkings) > 0:
                selected_parking = self.parkings[0]
        self.parking = selected_parking
        reference_parking = self.parkings[0] if len(self.parkings) > 0 else None
        # Gestion robuste si pas de parking
        if selected_parking is not None:
            car_parking_time = float(self.sim.car_time_to_parking(selected_parking))

            nb_libre = selected_parking.get("nb_libre") or 0
            nb_total = selected_parking.get("nb_total") or 0
            taux_parking = round(nb_libre / nb_total, 2) if nb_total > 0 else 0.0

            walk_time = float(selected_parking["walk_min"])

        else:
            car_parking_time = float(self.cfg.max_eta_min)
            taux_parking = 0.0
            walk_time = 0.0

        if reference_parking is not None:
            ref_car_parking_time = float(self.sim.car_time_to_parking(reference_parking))
            ref_walk_time = float(reference_parking["walk_min"])
        else:
            ref_car_parking_time = float(self.cfg.max_eta_min)
            ref_walk_time = 0.0

        arrival_to_station_ref = current_time + ref_car_parking_time + ref_walk_time
        arrival_to_station_selected = current_time + car_parking_time + walk_time

        if self.station_id is None:
            train_wait_ref = float(self.cfg.max_wait_min)
            train_wait = float(self.cfg.max_wait_min)
            train_trip = float(self.cfg.max_trip_min)
        else:
            try:
                train_wait_ref = float(
                    self.ts.train_wait_time_from_trips_realtime(
                        self.station_id, self.dest_id, arrival_to_station_ref
                    )
                )
                train_wait = float(
                    self.ts.train_wait_time_from_trips_realtime(
                        self.station_id, self.dest_id, arrival_to_station_selected
                    )
                )
                train_trip = float(
                    self.ts.gtfs.train_trip_time(self.station_id, self.dest_id)
                )
            except Exception:
                train_wait_ref = float(self.cfg.max_wait_min)
                train_wait = float(self.cfg.max_wait_min)
                train_trip = float(self.cfg.max_trip_min)

        time_car = car_dest_time
        time_train = car_parking_time + walk_time + train_wait + train_trip
        time_train_ref = ref_car_parking_time + ref_walk_time + train_wait_ref + train_trip
        denom = max(time_car, time_train, time_train_ref, 1.0)


        if len(self.parkings) > 1:
            parking_2 = self.parkings[1]
            car_parking_time_2 = float(self.sim.car_time_to_parking(parking_2))
            walk_time_2 = float(parking_2["walk_min"])
            arrival_to_station_2 = current_time + car_parking_time_2 + walk_time_2

            try:
                train_wait_2 = float(
                    self.ts.train_wait_time_from_trips_realtime(
                        self.station_id, self.dest_id, arrival_to_station_2
                    )
                )
                train_trip_2 = float(
                    self.ts.gtfs.train_trip_time(self.station_id, self.dest_id)
                )
            except Exception:
                train_wait_2 = float(self.cfg.max_wait_min)
                train_trip_2 = float(self.cfg.max_trip_min)

            time_train_2 = car_parking_time_2 + walk_time_2 + train_wait_2 + train_trip_2
        else:
            time_train_2 = float("inf")

        best_time = min(time_car, time_train_ref, time_train_2)

        # Reward principale liée au temps
        if int(action) == 0:
            total_time = time_car
            mode = "car_direct"
            reward_temps = (best_time - time_car) / max(best_time, time_car, 1.0)

        elif int(action) == 1:
            total_time = time_train
            mode = "park_nearest"
            reward_temps = (best_time - time_train) / max(best_time, time_train, 1.0)

        elif int(action) == 2:
            total_time = time_train
            mode = "park_second"
            reward_temps = (best_time - time_train) / max(best_time, time_train, 1.0)

        else:
            raise ValueError(f"Action non reconnue: {action}")

        # Pénalité liée au taux de dispo parking, seulement si action=train
        parking_penalty = 0.0
        if int(action)  in [1, 2]:
            parking_penalty = lambda_parking * (1.0 - taux_parking)

        self.reward = reward_temps - parking_penalty
        with open(self.log_file, "a") as f:
            f.write(f"{self.episode_count},{self.reward},{time.time()}\n")


        self.terminated = True
        self.truncated = False

        info = {
        "station_id": self.station_id,
        "parking_id": selected_parking["parking_id"] if selected_parking else None,
        "parking_name": selected_parking["nom"] if selected_parking else None,
        "action": int(action),
        "mode": mode,
        "time_min_at_decision": current_time,
        "car_dest_time": car_dest_time,
        "car_parking_time": car_parking_time,
        "walk_time": walk_time,
        "train_wait_min": train_wait,
        "train_trip_min": train_trip,
        "time_car": time_car,
        "time_train": time_train,
        "taux_parking": taux_parking,
        "reward_temps": float(reward_temps),
        "parking_penalty": float(parking_penalty),
        "total_time_min": float(total_time),
        "reward": float(self.reward),
        "done_reason": "decision_made",
        }

        obs = self._get_observation()
        return obs, float(self.reward), self.terminated, self.truncated, info
    # ── Render ────────────────────────────────────────────────────────────────

    def render(self, mode="human"):
        if mode != "human":
            return

        m = self.current_metrics or {}
        print(
            f"Step={self.current_steps} | "
            f"Terminated={self.terminated} | "
            f"Truncated={self.truncated} | "
            f"Reward={self.reward:.3f} | "
            f"Station={self.station_id} | "
            f"Dest={self.dest_id} | "
            f"Time={m.get('time_min', 0.0):.1f} min | "
            f"Dist_station={m.get('dist_to_station_km', 0.0):.2f} km | "
            f"Dist_dest={m.get('dist_to_dest_km', 0.0):.2f} km | "
            f"Traffic={m.get('traffic', 0.0):.2f}"
        )


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    env = ParkOrRideMulti()

    print("=== RESET ENV ===")
    obs, info = env.reset()
    print("Observation:", obs)
    print("Info:", info)

    done = False
    step = 0

    while not done:
        step += 1
        action = env.action_space.sample()

        print(f"\n=== STEP {step} ===")
        if action == 0:
            action_label = "voiture"
        elif action == 1:
            action_label = "train + parking 1"
        else:
            action_label = "train + parking 2"

        print("Action:", action, "→", action_label)

        obs, reward, terminated, truncated, info = env.step(action)

        print("Observation:", obs)
        print("Reward:", reward)
        print("Terminated:", terminated)
        print("Truncated:", truncated)
        print("Info:", info)

        env.render()
        done = terminated or truncated

    print("\n=== EPISODE FINISHED ===")


if __name__ == "__main__":
    main()