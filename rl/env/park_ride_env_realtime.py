import numpy as np
import gymnasium as gym
import sys
import os
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from rl.simulators.car_simulatorRL import CarSimulator
from src.realtime.transit_realtime_service import TransitRealtimeService
from src.gtfs_service import GTFSService
from parking.parking_servicert import ParkingServiceRT
from rl.env.cfg import Configurator
from sklearn.preprocessing import RobustScaler


OBS_SIZE = 10

DEFAULT_SYNC_TTL = 10*60


class TrainFeatureScaler:
    """
    Robust scaler for train wait and trip features using median and IQR.
    Uses scikit-learn's RobustScaler fitted on GTFS statistics.
    """
    def __init__(self, gtfs_service: GTFSService = None):
        self.scaler_wait = RobustScaler(quantile_range=(25.0, 75.0))
        self.scaler_trip = RobustScaler(quantile_range=(25.0, 75.0))
        self._fit_scalers(gtfs_service)

    def _fit_scalers(self, gtfs_service: GTFSService = None):
        if gtfs_service is None:
            gtfs_service = GTFSService()

        try:
            stop_times = gtfs_service._stop_times.copy()

            trip_durations = stop_times.groupby('trip_id').apply(
                lambda x: x['arrival_min'].max() - x['departure_min'].min()
            ).values.reshape(-1, 1)

            if len(trip_durations) > 0:
                self.scaler_trip.fit(trip_durations)

            departures = stop_times.groupby('stop_id')['departure_min'].apply(
                lambda x: np.diff(np.sort(x))
            )
            wait_times = np.concatenate([w for w in departures if len(w) > 0]).reshape(-1, 1)

            if len(wait_times) > 0:
                self.scaler_wait.fit(wait_times)

            print("[INFO] TrainFeatureScaler fitted on GTFS data")
        except Exception as e:
            print(f"[WARNING] Could not fit TrainFeatureScaler on GTFS data: {e}")
            self.scaler_wait.fit(np.array([[0], [60], [120]]))
            self.scaler_trip.fit(np.array([[0], [60], [120]]))

    def scale_wait(self, value: float) -> float:
        if not np.isfinite(value):
            value = 120.0
        scaled = self.scaler_wait.transform(np.array([[value]]))[0, 0]
        return float(np.clip(scaled, 0.0, 1.0))

    def scale_trip(self, value: float) -> float:
        if not np.isfinite(value):
            value = 120.0
        scaled = self.scaler_trip.transform(np.array([[value]]))[0, 0]
        return float(np.clip(scaled, 0.0, 1.0))


def minutes_to_time_str(minutes: float) -> str:
    total_seconds = int(round(minutes * 60))
    total_seconds = total_seconds % (24 * 3600)
    h = total_seconds // 3600
    m = (total_seconds % 3600) // 60
    s = total_seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


class ParkOrRide(gym.Env):
    """
    Gym Environment for Park-or-Ride (1 gare, 1 parking).

    Actions:
        0 → continuer en voiture jusqu'à destination
        1 → Park & Ride (garer au parking, marcher, prendre le train)

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

    Scénarios au reset :
        scenario=0 : position et destination aléatoires (comportement originel)
        scenario=1 : scénario train favorable — gare choisie proche d'un parking,
                     destination optimale (meilleur temps d'attente), détour voiture
                     injecté pour allonger le trajet par la route.

    Synchronisation temps réel :
        sync_realtime(force=False) rafraîchit parking + transit en une seule
        passe, avec un TTL configurable (sync_ttl secondes). Appelée
        automatiquement au reset et exposée publiquement.
    """

    metadata = {"render_modes": ["human"], "render_fps": 30}

    def __init__(
        self,
        env_id: int = 0,
        scenario_prob: float = 0.5,
        sync_ttl: float = DEFAULT_SYNC_TTL,
    ):
        super().__init__()

        self.env_id = env_id
        self.sync_ttl = float(sync_ttl)
        self._last_sync_ts: float = 0.0

        self.ts = TransitRealtimeService()
        self.ps = ParkingServiceRT()
        self.cfg = Configurator()

        self.sync_realtime(force=True)

        self.train_scaler = TrainFeatureScaler(self.ts.gtfs)

        self.sim = CarSimulator(
            scenario_prob=scenario_prob,
            sync_realtime_callback=self._sim_sync_callback,
        )

        self.truncated = False
        self.terminated = False
        self.reward = 0.0
        self.current_steps = 0
        self.dest_id = None
        self.station = None
        self.station_id = None
        self.parking = None
        self.current_metrics = {}
        self.episode_count = 0
        self.current_scenario = 0

        os.makedirs("logs", exist_ok=True)
        self.log_file = f"logs/rewards_env_{env_id}.csv"

        self.observation_space = gym.spaces.Box(
            low=np.zeros(OBS_SIZE, dtype=np.float32),
            high=np.ones(OBS_SIZE, dtype=np.float32),
            dtype=np.float32,
        )
        self.action_space = gym.spaces.Discrete(2)

    def sync_realtime(self, force: bool = False) -> bool:
        now = time.time()
        if not force and (now - self._last_sync_ts) < self.sync_ttl:
            return False

        errors = []

        try:
            self.ts.refresh()
        except Exception as e:
            errors.append(f"transit: {e}")

        try:
            self.ps.refresh()
        except Exception as e:
            errors.append(f"parking: {e}")

        self._last_sync_ts = time.time()

        if errors:
            print(f"[ParkOrRide] sync_realtime partielle — erreurs: {'; '.join(errors)}")
        else:
            print(f"[ParkOrRide] sync_realtime OK (env_id={self.env_id})")

        return True

    def _sim_sync_callback(self):
        self.sync_realtime(force=False)

    def _norm(self, value: float, max_value: float) -> float:
        if max_value <= 0:
            return 0.0
        return float(np.clip(value / max_value, 0.0, 1.0))

    def _get_observation(self, time_ref: float = None) -> np.ndarray:
        metrics = self.sim.get_metrics() or {}
        self.current_metrics = metrics

        dist_dest    = metrics.get("dist_to_dest_km",    0.0)
        dist_station = metrics.get("dist_to_station_km", 0.0)
        dist_parking = metrics.get("dist_to_parking_km", 0.0)
        traffic      = metrics.get("traffic",            0.0)
        time_min     = metrics.get("time_min",           0.0)

        eta_car_dest    = float(self.sim.car_time_to_dest())
        if time_ref is None:
            time_ref = time_min
        eta_car_parking = float(self.sim.car_time_to_parking(self.parking, self.cfg.max_eta_car_parking))

        if self.station_id is None:
            train_wait = float(self.cfg.max_wait_min)
            train_trip = float(self.cfg.max_trip_min)
        else:
            try:
                train_wait = float(self.ts.train_wait_time_from_trips_realtime(
                    self.station_id, self.dest_id, time_ref
                ))
                train_trip = float(self.ts.gtfs.train_trip_time(
                    self.station_id, self.dest_id
                ))
            except Exception as e:
                print(f"[WARN] train_wait exception: {e}")
                train_wait = float(self.cfg.max_wait_min)
                train_trip = float(self.cfg.max_trip_min)

        if not np.isfinite(train_wait):
            train_wait = float(self.cfg.max_wait_min)
        if not np.isfinite(train_trip):
            train_trip = float(self.cfg.max_trip_min)

        if self.parking is not None:
            taux_parking, _ = self.ps.get_parking_availability(self.parking)
        else:
            taux_parking = 0.0

        time_of_day = (time_min % (24 * 60)) / (24 * 60)

        obs = np.array([
            self._norm(dist_dest,       self.cfg.max_dist_dest_km),
            self._norm(dist_station,    self.cfg.max_dist_dest_km),
            float(time_of_day),
            self.ps.scale_dist_parking(dist_parking, self.cfg.max_dist_parking_km),
            float(np.clip(traffic,      0.0, 1.0)),
            self._norm(eta_car_dest,    self.cfg.max_eta_min),
            self._norm(eta_car_parking, self.cfg.max_eta_min),
            self.train_scaler.scale_wait(train_wait),
            self.train_scaler.scale_trip(train_trip),
            float(np.clip(taux_parking, 0.0, 1.0)),
        ], dtype=np.float32)

        return obs

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)

        self.sync_realtime(force=False)

        self.truncated = False
        self.terminated = False
        self.reward = 0.0
        self.current_steps = 0
        self.station = None
        self.station_id = None
        self.parking = None
        self.current_metrics = {}
        self.episode_count += 1

        self.sim.reset(
            seed=seed,
            parking_service=self.ps,
            transit_service=self.ts,
        )
        self.dest_id = self.sim.get_dest_id()
        self.current_scenario = self.sim.current_scenario

        for _ in range(self.cfg.max_iterations):
            self.current_steps += 1
            self.sim.advance(self.cfg.dt_min)

            candidate = self.sim.get_closest_station()
            if candidate is None:
                continue
            dist_station = self.sim.distance_to(candidate["lat"], candidate["lon"])
            if dist_station <= self.cfg.decision_distance_km:
                self.station_id = candidate["id"]
                self.station = {
                    "id":  candidate["id"],
                    "lat": candidate["lat"],
                    "lon": candidate["lon"],
                }
                self.parking = self.ps.get_best_parking_for_station(self.station)
                self.sim.parking = self.parking

                _current_time     = float(self.sim.get_time_min())
                _car_parking_time = float(self.sim.car_time_to_parking(self.parking, self.cfg.max_eta_car_parking))
                _walk_time        = float(self.ps.get_walk_time_station_parking(self.station))
                _arrival          = _current_time + _car_parking_time + _walk_time

                obs = self._get_observation(time_ref=_arrival)
                info = {
                    "reset":      "success",
                    "station_id": self.station_id,
                    "dest_id":    self.dest_id,
                    "parking_id": self.parking["parking_id"] if self.parking else None,
                    "scenario":   self.current_scenario,
                }
                return obs, info

        self.truncated = True
        obs  = self._get_observation()
        info = {"reset": "truncated_before_decision", "scenario": self.current_scenario}
        return obs, info

    def step(self, action):
        if not self.action_space.contains(action):
            raise ValueError(f"Invalid action: {action}")

        if self.truncated or self.terminated:
            obs = self._get_observation()
            return obs, 0.0, True, True, {"state": "already_ended"}

        if int(action) == 1 and self.parking is None:
            obs = self._get_observation()
            self.terminated = True
            return obs, -1.0, True, False, {
                "done_reason": "no_parking",
                "parking_id": None,
                "car_dest_time": float(self.sim.car_time_to_dest()),
                "car_parking_time": 0.0,
                "walk_time": 0.0,
                "train_wait_min": 0.0,
                "train_trip_min": 0.0,
                "scenario": self.current_scenario,
            }

        lambda_parking = 0.1

        current_time     = float(self.sim.get_time_min())
        car_dest_time    = float(self.sim.car_time_to_dest())
        car_parking_time = float(self.sim.car_time_to_parking(self.parking, self.cfg.max_eta_car_parking))
        taux_parking, _  = self.ps.get_parking_availability(self.parking)

        walk_time          = float(self.ps.get_walk_time_station_parking(self.station))
        arrival_to_station = current_time + car_parking_time + walk_time

        if self.station_id is None:
            train_wait = float(self.cfg.max_wait_min)
            train_trip = float(self.cfg.max_trip_min)
        else:
            try:
                train_wait = float(
                    self.ts.train_wait_time_from_trips_realtime(
                        self.station_id, self.dest_id, arrival_to_station
                    )
                )
                train_trip = float(
                    self.ts.gtfs.train_trip_time(self.station_id, self.dest_id)
                )
            except Exception:
                train_wait = float(self.cfg.max_wait_min)
                train_trip = float(self.cfg.max_trip_min)

        if not np.isfinite(train_wait):
            train_wait = float(self.cfg.max_wait_min)
        if not np.isfinite(train_trip):
            train_trip = float(self.cfg.max_trip_min)

        time_car   = car_dest_time
        time_train = car_parking_time + walk_time + train_wait + train_trip
        denom      = max(time_car, time_train, 1.0)

        if int(action) == 0:
            total_time      = time_car
            average_traffic = self.sim.compute_average_traffic(time_car)
            mode            = "car"
            reward_temps    = (time_train - time_car) / denom
        else:
            total_time   = time_train
            mode         = "train"
            reward_temps = (time_car - time_train) / denom

        parking_penalty = 0.0
        traffic_penalty = 0.0
        if int(action) == 1:
            parking_penalty = self.cfg.parking_factor * (1.0 - taux_parking)
        else:
            traffic_penalty = self.cfg.traffic_factor * (average_traffic)

        self.reward = reward_temps - parking_penalty - traffic_penalty

        with open(self.log_file, "a") as f:
            import time as _time
            f.write(f"{self.episode_count},{self.reward},{_time.time()},{self.current_scenario}\n")

        self.terminated = True
        self.truncated  = False

        info = {
            "station_id":         self.station_id,
            "parking_id":         self.parking["parking_id"] if self.parking else None,
            "time_min_at_decision": current_time,
            "car_dest_time":      car_dest_time,
            "car_parking_time":   car_parking_time,
            "walk_time":          walk_time,
            "train_wait_min":     train_wait,
            "train_trip_min":     train_trip,
            "time_car":           time_car,
            "time_train":         time_train,
            "taux_parking":       taux_parking,
            "reward_temps":       float(reward_temps),
            "parking_penalty":    float(parking_penalty),
            "mode":               mode,
            "total_time_min":     float(total_time),
            "reward":             float(self.reward),
            "done_reason":        "decision_made",
            "scenario":           self.current_scenario,
        }

        obs = self._get_observation(time_ref=arrival_to_station)
        return obs, float(self.reward), self.terminated, self.truncated, info

    def render(self, mode="human"):
        if mode != "human":
            return

        m = self.current_metrics or {}
        print(
            f"Step={self.current_steps} | "
            f"Scenario={self.current_scenario} | "
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


def test_reachable(gtfs_service):

    origin = "StopPoint:OCETrain TER-87581801"

    print("===================================")
    print("Origin station:", origin)
    print("===================================")

    reachable = gtfs_service.get_reachable_stations(origin)

    if reachable.empty:
        print("Aucune station atteignable.")
        return

    print(f"{len(reachable)} stations atteignables :\n")

    for _, row in reachable.iterrows():

        dest_id = row["destination_station_id"]
        name = row["destination_name"]
        lat = row["destination_lat"]
        lon = row["destination_lon"]

        try:
            trip_time = gtfs_service.train_trip_time(origin, dest_id)
        except Exception:
            trip_time = None

        print(
            f"{dest_id} | {name} | trip ≈ {trip_time:.1f} min"
            if trip_time is not None
            else f"{dest_id} | {name}"
        )

def main():
    env = ParkOrRide(scenario_prob=0.5, sync_ttl=180)

    n_episodes = 100

    valid_episodes = 0
    train_better_count = 0
    correct_action_count = 0

    for ep in range(n_episodes):
        print(f"\n================ EPISODE {ep + 1} ================")

        obs, info = env.reset()
        print("Scénario:", info.get("scenario"), "(0=aléatoire, 1=train favorable)")
        print("Reset info:", info)

        action = env.action_space.sample()
        action_name = "voiture" if action == 0 else "train"

        obs, reward, terminated, truncated, info = env.step(action)

        time_car = info.get("time_car")
        time_train = info.get("time_train")

        if time_car is None or time_train is None:
            print("Épisode invalide:", info)
            continue

        valid_episodes += 1

        if time_train < time_car:
            optimal_action = 1
            optimal_name = "train"
            train_better_count += 1
        else:
            optimal_action = 0
            optimal_name = "voiture"

        if action == optimal_action:
            correct_action_count += 1

        print(f"Action prise    : {action_name}")
        print(f"Action optimale : {optimal_name}")
        print(f"Temps voiture   : {time_car:.2f} min")
        print(f"Temps train     : {time_train:.2f} min")
        print(f"Reward          : {reward:.3f}")

        if action == optimal_action:
            print("Décision correcte")
        else:
            print("Décision non optimale")

    print("\n================ BILAN FINAL ================")

    if valid_episodes == 0:
        print("Aucun épisode valide.")
        return

    train_better_percent = 100 * train_better_count / valid_episodes
    correct_action_percent = 100 * correct_action_count / valid_episodes

    print(f"Épisodes valides : {valid_episodes}/{n_episodes}")
    print(
        f"Train plus rapide : {train_better_count}/{valid_episodes} "
        f"({train_better_percent:.2f} %)"
    )
    print(
        f"Action optimale choisie : {correct_action_count}/{valid_episodes} "
        f"({correct_action_percent:.2f} %)"
    )

if __name__ == "__main__":
    gtfs = GTFSService()
    test_reachable(gtfs)
    main()