import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv, VecMonitor
from stable_baselines3.common.callbacks import CheckpointCallback
from rl.callbacks.decision_logger import DecisionLoggerCallback

from .config import PPOConfig
from .utils import ensure_dirs, set_global_seed

from pathlib import Path 


from rl.env.park_ride_env_realtime import ParkOrRide
from datetime import datetime






def main():

    cfg = PPOConfig()
    ensure_dirs(cfg.models_dir, cfg.logs_dir)
    set_global_seed(cfg.seed)

    def make_env(env_id):
        def _init():
            env = ParkOrRide(env_id=env_id)
            return env
        return _init
    
    env_parallel = DummyVecEnv([make_env(i) for i in range(cfg.n_envs)])
    env_parallel = VecMonitor(env_parallel) 

    checkpoint_callback = CheckpointCallback(
        save_freq=cfg.save_freq,
        save_path=cfg.models_dir,
        name_prefix=cfg.model_name,
    )

    model = PPO(
        "MlpPolicy",
        env_parallel,
        learning_rate=cfg.learning_rate,
        n_steps=cfg.n_steps,
        batch_size=cfg.batch_size,
        gamma=cfg.gamma,
        gae_lambda=cfg.gae_lambda,
        clip_range=cfg.clip_range,
        ent_coef=cfg.ent_coef,
        verbose=1,
        tensorboard_log=cfg.logs_dir,
    )

    model.learn(
        total_timesteps=cfg.total_timesteps,
        tb_log_name="PPO",
        reset_num_timesteps=True,
        callback=[checkpoint_callback, DecisionLoggerCallback()],
    )
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    model_filename = f"{cfg.model_name}_{timestamp}"
    model.save(f"{cfg.models_dir}/{model_filename}")

main()