import numpy as np
import gymnasium as gym

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

    def __init__(self, car_simulator, train_service, configurator):
        super().__init__()
        self.sim = car_simulator
        self.ts = train_service
        self.cfg = configurator
        self.truncated = False
        self.terminated = False
        self.reward = 0.0
        self.current_steps = 0
        self.station_id = None
        self.current_metrics = {}

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
        """Normalize value into [0,1]"""
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
        metrics = self.sim.get_metrics()
        self.current_metrics = metrics

        dist_station = metrics.get("dist_to_station_km", self.cfg.max_dist_station_km)
        dist_dest = metrics.get("dist_to_dest_km", self.cfg.max_dist_dest_km)
        traffic = np.clip(metrics.get("traffic_level", 0.5), 0.0, 1.0)
        time_min = metrics.get("time_min", 0.0)

        eta_car_dest = self.sim.car_time_to_dest()
        eta_car_station = self.sim.car_time_to_station()

        if self.station_id is None:
            train_wait = self.cfg.max_wait_min
            train_trip = self.cfg.max_trip_min
        else:
            train_wait = self.ts.train_wait_time(self.station_id, time_min)
            train_trip = self.ts.train_trip_time(self.station_id)

        obs = np.array(
            [
                self._norm(dist_station, self.cfg.max_dist_station_km),
                self._norm(dist_dest, self.cfg.max_dist_dest_km),
                traffic,
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
        2. Advance until vehicle is near a station 
        3. Set current station_id
        4. Return initial observation
        """
        self.sim.reset(seed=seed)

        self.truncated = False
        self.terminated = False
        self.reward = 0.0
        self.current_steps = 0
        self.station_id = None
        self.current_metrics = {}

        for _ in range(self.cfg.max_iterations):
            self.current_steps += 1

            self.sim.advance(self.cfg.dt_min)

            dist_station = self.sim.get_dist_to_station_km()

            if dist_station <= self.cfg.decision_distance_km:
                self.station_id = self.sim.get_closest_station_id()

                current_time = self.sim.get_time_min()

                if hasattr(self.ts, "reset"):
                    self.ts.reset(self.station_id, current_time)

                obs = self._get_observation()
                return obs, {"reset": "success", "station_id": self.station_id}

        self.truncated = True
        obs = self._get_observation()
        return obs, {"reset": "truncated_before_decision"}

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
            return self._get_observation(), 0.0, True, True, {"state": "already_ended"}

        current_time = self.sim.get_time_min()
        car_station_time = self.sim.car_time_to_station()
        car_dest_time = self.sim.car_time_to_dest()

        if self.station_id is None:
            train_wait = self.cfg.max_wait_min
            train_trip = self.cfg.max_trip_min
        else:
            train_wait = self.ts.train_wait_time(self.station_id, current_time)
            train_trip = self.ts.train_trip_time(self.station_id)

        info = {
            "station_id": self.station_id,
            "time_min_at_decision": current_time,
            "car_time_to_station_min": car_station_time,
            "car_time_to_dest_min": car_dest_time,
            "train_wait_min": train_wait,
            "train_trip_min": train_trip,
        }

        if action == 0:
            total_time = car_dest_time
            mode = "car"
        else:
            total_time = car_station_time + train_wait + train_trip
            mode = "train"

        self.reward = -self.cfg.reward_factor * total_time
        self.terminated = True
        self.truncated = False

        info.update(
            {
                "mode": mode,
                "total_time_min": total_time,
                "reward": self.reward,
                "done_reason": "decision_made",
            }
        )

        obs = self._get_observation()
        return obs, float(self.reward), True, False, info

    def render(self, mode="human"):
        """Debug rendering"""
        if mode != "human":
            return

        m = self.current_metrics if self.current_metrics else {}
        print(
            f"Step={self.current_steps} | "
            f"Terminated={self.terminated} | "
            f"Truncated={self.truncated} | "
            f"Reward={self.reward:.2f} | "
            f"Station={self.station_id} | "
            f"Time={m.get('time_min', None)} | "
            f"Dist_station={m.get('dist_to_station_km', None)} | "
            f"Dist_dest={m.get('dist_to_dest_km', None)} | "
            f"Traffic={m.get('traffic_level', None)}"
        )