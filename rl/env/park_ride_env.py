import numpy as np
import gymnasium as gym

from rl.simulators.car_simulator import CarSimulator
from src.gtfs_service import GTFSService
from parking.parking_service import ParkingServiceOSRM
from rl.env.cfg import Configurator
class ParkOrRide(gym.Env):
    """
    Gym Environment for Park-or-Ride (V1 SIMPLE VERSION - NO PARKING).

    Actions:
        0 -> Continue by car
        1 -> Take train (parking assumed immediately available, walk time = 0)

    Design:
        - reset(): advances simulation until near a station (decision point)
        - step(): single decision episode (terminated after one action)
    """

    metadata = {"render_modes": ["human"], "render_fps": 30}
    def __init__(self):

        super().__init__()
        car_sim = CarSimulator() 
        train_svc = GTFSService() 
        parking_svc=ParkingServiceOSRM()
        config = Configurator()
        self.sim = car_sim
        self.ts = train_svc
        self.ps=parking_svc
        self.cfg = config

        self.truncated = False
        self.terminated = False
        self.reward = 0.0
        self.current_steps = 0
        self.station_id = None
        self.current_metrics = {}
        self.parking=None
        self.dest_id=None
        # Observation:
        # [dist_station, dist_dest, traffic, eta_car_dest, eta_car_station, train_wait, train_trip]
        self.observation_space = gym.spaces.Box(
            low=np.zeros(7, dtype=np.float32),
            high=np.ones(7, dtype=np.float32),
            dtype=np.float32,
        )

        # Actions: 0 = car, 1 = train
        self.action_space = gym.spaces.Discrete(2)

    def _norm(self, value, max_value):
        if max_value <= 0:
            return 0.0
        return float(np.clip(value / max_value, 0.0, 1.0))
    def _get_observation(self):
        """
        Build observation vector from:
        - Car simulator metrics
        - Car ETA functions
        - Train service (wait + trip)
        """
        metrics = self.sim.get_metrics() or {}
        self.current_metrics = metrics

        dist_station =metrics["dist_to_station_km"]
        dist_dest =metrics["dist_to_dest_km"]
        traffic =metrics["traffic"]
        time_min = metrics["time_min"]
        time_str=metrics["time_str"]
        eta_car_dest = float(self.sim.car_time_to_dest())
        eta_car_station = float(self.sim.car_time_to_station())

        if self.station_id is None:
            train_wait = float(self.cfg.max_wait_min)
            train_trip = float(self.cfg.max_trip_min)
        else:
            train_wait = float(self.ts.train_wait_time(self.station_id, time_str))
            train_trip = float(self.ts.train_trip_time(self.station_id))

        obs = np.array(
            [
                self._norm(dist_station, self.cfg.max_dist_station_km),
                self._norm(dist_dest, self.cfg.max_dist_dest_km),
                float(np.clip(traffic, 0.0, 1.0)),
                self._norm(eta_car_dest, self.cfg.max_eta_min),
                self._norm(eta_car_station, self.cfg.max_eta_min),
                self._norm(train_wait, self.cfg.max_wait_min),
                self._norm(train_trip, self.cfg.max_trip_min),
            ],
            dtype=np.float32,
        )

        return obs

    def reset(self, seed=None, options=None):
        """
        Reset environment:
        1. Reset car simulator scenario
        2. Advance until vehicle is near a station (decision point)
        3. Set current station_id
        4. Return initial observation
        """
        super().reset(seed=seed)

        self.sim.reset(seed=seed)
        self.dest_id=self.sim.get_dest_id()
        self.truncated = False
        self.terminated = False
        self.reward = 0.0
        self.current_steps = 0
        self.station_id = None
        self.current_metrics = {}

        for _ in range(self.cfg.max_iterations):
            self.current_steps += 1
            self.sim.advance(self.cfg.dt_min)
            dist_station = float(self.sim.get_dist_to_station_km())
            if dist_station <= self.cfg.decision_distance_km:
                self.station_id = self.sim.get_closest_station_id()
                self.parking=self.ps.get_best_parking_for_station(self.station_id)
                obs = self._get_observation()
                info = {"reset": "success", "station_id": self.station_id,"parking_id":self.parking["id"]}
                return obs, info

        # Pas arrivé au point de décision
        self.truncated = True
        obs = self._get_observation()
        info = {"reset": "truncated_before_decision"}
        return obs, info

    def step(self, action):
        """
        Single decision step:
            0 -> continue by car
            1 -> take train (parking assumed next to station)
        Episode terminates immediately after decision.
        """
        if not self.action_space.contains(action):
            raise ValueError(f"Invalid action: {action}")

        if self.truncated or self.terminated:
            obs = self._get_observation()
            return obs, 0.0, True, True, {"state": "already_ended"}

        current_time = float(self.sim.get_time_min())
        car_parking_time = float(self.sim.car_time_to_parking(self.parking))
        car_dest_time = float(self.sim.car_time_to_dest())
        walk_time=self.ps.get_walk_time_station_parking(self.station_id)
        arrival_to_station_time=current_time+walk_time
        if self.station_id is None:
            train_wait = float(self.cfg.max_wait_min)
            train_trip = float(self.cfg.max_trip_min)
        else:
            train_wait = float(self.ts.train_wait_time(self.station_id,arrival_to_station_time))
            #################MANAL

            train_trip = float(self.ts.train_trip_time(self.station_id,self.dest_id)) 

        info = {
            "station_id": self.station_id,
            "time_min_at_decision": current_time,
            "car_time_to_parking_min": car_parking_time,
            "car_time_to_dest_min": car_dest_time,
            "walk_time":walk_time,
            "train_wait_min": train_wait,
            "train_trip_min": train_trip,
        }

        if int(action) == 0:
            total_time = car_dest_time
            mode = "car"
        else:
            total_time = car_parking_time +walk_time+ train_wait + train_trip
            mode = "train"

        self.reward = -float(self.cfg.reward_factor) * float(total_time)
        self.terminated = True
        self.truncated = False

        info.update(
            {
                "mode": mode,
                "total_time_min": float(total_time),
                "reward": float(self.reward),
                "done_reason": "decision_made",
            }
        )

        obs = self._get_observation()
        return obs, float(self.reward), self.terminated, self.truncated, info

    def render(self, mode="human"):
        if mode != "human":
            return

        m = self.current_metrics or {}
        time_in_min = self._safe_metric(m, "time_min", default=None)
        dist_stat = self._safe_metric(m, "dist_to_station_km", "distance_to_station_km", default=None)
        dist_dest = self._safe_metric(m, "dist_to_dest_km", "distance_to_dest_km", default=None)
        traf = self._safe_metric(m, "traffic", "saturation", default=None)

        print(
            f"Step={self.current_steps} | "
            f"Terminated={self.terminated} | "
            f"Truncated={self.truncated} | "
            f"Reward={self.reward:.2f} | "
            f"Station={self.station_id} | "
            f"Time={time_in_min} | "
            f"Dist_station={dist_stat} | "
            f"Dist_dest={dist_dest} | "
            f"Traffic={traf}"
        )