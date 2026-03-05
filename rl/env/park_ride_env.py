import numpy as np
import gymnasium as gym

from rl.simulators.car_simulator import CarSimulator
from src.gtfs_service import GTFSService
from parking.parking_service import ParkingServiceOSRM
from rl.env.cfg import Configurator
def minutes_to_time_str(minutes: float) -> str:
    total_seconds = int(round(minutes * 60))
    total_seconds = total_seconds % (24 * 3600)  # modulo 24h
    h = total_seconds // 3600
    m = (total_seconds % 3600) // 60
    s = total_seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"
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
    def minutes_to_time_str(self,minutes):
        """
        Convertit un temps en minutes en format "HH:MM:SS"
        
        Exemple:
            90 -> "01:30:00"
            385.5 -> "06:25:30"
        """
        total_seconds = int(round(minutes * 60))
        
        h = total_seconds // 3600
        m = (total_seconds % 3600) // 60
        s = total_seconds % 60
    
        return f"{h:02d}:{m:02d}:{s:02d}"
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
        time_str=self.minutes_to_time_str(time_min)
        eta_car_dest = float(self.sim.car_time_to_dest())
        eta_car_station = float(self.sim.car_time_to_station())

        if self.station_id is None:
            train_wait = float(self.cfg.max_wait_min)
            train_trip = float(self.cfg.max_trip_min)
        else:
            print("PROBLEM",self.dest_id)
            train_wait = float(self.ts.train_wait_time_from_trips(self.station_id, self.dest_id,time_min))

            train_trip = float(self.ts.train_trip_time(self.station_id,self.dest_id))

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
        print("COOOUCOU",self.dest_id)
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
                print(self.station_id)
                print(self.dest_id)
                self.parking=self.ps.get_best_parking_for_station(self.station_id)
                print("PARKING",self.parking)
                obs = self._get_observation()
                info = {"reset": "success", "station_id": self.station_id,"dest_id":self.dest_id,"parking_id":self.parking["parking_id"]}
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
        print("PARKING",self.parking)
        print("CAR PARKING TIMMME ",car_parking_time)
        car_dest_time = float(self.sim.car_time_to_dest())
        walk_time=self.ps.get_walk_time_station_parking(self.station_id)
        arrival_to_station_time=current_time+car_parking_time+walk_time
        if self.station_id is None:
            train_wait = float(self.cfg.max_wait_min)
            train_trip = float(self.cfg.max_trip_min)
        else:
            train_wait=self.ts.train_wait_time_from_trips(self.station_id,self.dest_id,arrival_to_station_time)
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
       print("PARKING",self.parking)
        print("CAR PARKING TIMMME ",car_parking_time)
            total_time = car_parking_time +walk_time+ train_wait + train_trip

            mode = "train"
        self.reward = -float(self.cfg.reward_factor) * float(total_time)
        print("REWARD: \n",self.reward)
        print("ACTION: \n",action)
        print("train wait min",train_wait)
        print("train trip time",train_trip)
        print("car time to parking",car_parking_time)
        print("car time to dest",car_dest_time)
        print("heure actuelle",minutes_to_time_str(current_time))
        print("heure de depart du train",minutes_to_time_str(train_wait+current_time))
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
        time_in_min = m["time_min"]
        dist_stat = m["dist_to_station_km"]
        dist_dest = m["dist_to_dest_km"]
        traf = m["traffic"]

        print(
            f"Step={self.current_steps} | "
            f"Terminated={self.terminated} | "
            f"Truncated={self.truncated} | "
            f"Reward={self.reward:.2f} | "
            f"Station={self.station_id} | "
            f"Station_dest={self.dest_id} | "

            f"Time={time_in_min} | "
            f"Dist_station={dist_stat} | "
            f"Dist_dest={dist_dest} | "
            f"Traffic={traf}"
        )

import numpy as np

def main():
    env = ParkOrRide()

    print("=== RESET ENV ===")
    obs, info = env.reset()

    print("Observation:", obs)
    print("Info:", info)

    done = False
    step = 0

    while not done:
        step += 1

        # action aléatoire (0 = car, 1 = train)
        action = env.action_space.sample()

        print(f"\n=== STEP {step} ===")
        print("Action:", action)

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