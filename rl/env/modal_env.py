import numpy as np
import gymnasium as gym
from gymnasium import spaces

class ModalShiftEnv(gym.Env):
    """
    Env jouet : action 0=car, 1=train.
    Reward = -(temps choisi). L'agent apprend à choisir le mode le plus rapide.
    """
    metadata = {"render_modes": []}

    def __init__(self, episode_len: int = 30):
        super().__init__()
        self.episode_len = episode_len
        self.t = 0

        # Observation simple (6 features normalisées 0..1)
        self.observation_space = spaces.Box(low=0.0, high=1.0, shape=(6,), dtype=np.float32)
        self.action_space = spaces.Discrete(2)

        self._rng = np.random.default_rng(42)

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        if seed is not None:
            self._rng = np.random.default_rng(seed)
        self.t = 0
        obs = self._make_obs()
        info = {}
        return obs, info

    def step(self, action):
        self.t += 1

        # On simule un trafic (0..1) qui impacte voiture
        traffic = float(self._rng.random())
        car_time = 10.0 + 25.0 * traffic              # 10..35 min
        train_time = 12.0 + 8.0 * float(self._rng.random())  # 12..20 min

        if int(action) == 0:
            reward = -car_time
            chosen = "car"
        else:
            reward = -train_time
            chosen = "train"

        obs = self._make_obs(traffic=traffic, car_time=car_time, train_time=train_time)

        terminated = self.t >= self.episode_len
        truncated = False
        info = {
            "traffic": traffic,
            "car_time": car_time,
            "train_time": train_time,
            "chosen": chosen,
            "missed_train": False,
        }
        return obs, float(reward), terminated, truncated, info

    def _make_obs(self, traffic=None, car_time=None, train_time=None):
        # Si pas donné, on invente des valeurs cohérentes
        if traffic is None:
            traffic = float(self._rng.random())
        if car_time is None:
            car_time = 10.0 + 25.0 * traffic
        if train_time is None:
            train_time = 12.0 + 8.0 * float(self._rng.random())

        # Features normalisées 0..1 (juste pour apprendre)
        dist_norm = float(self._rng.random())
        traffic_norm = traffic
        car_norm = (car_time - 10.0) / 25.0      # 0..1
        train_norm = (train_time - 12.0) / 8.0   # 0..1
        delay_norm = float(self._rng.random())   # fictif
        time_to_depart_norm = float(self._rng.random())  # fictif

        return np.array(
            [dist_norm, traffic_norm, car_norm, train_norm, delay_norm, time_to_depart_norm],
            dtype=np.float32
        )
