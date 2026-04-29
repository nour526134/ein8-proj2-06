import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from rl.env.park_ride_env import ParkOrRide
from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv, VecMonitor
from stable_baselines3.common.monitor import Monitor
from stable_baselines3.common.callbacks import BaseCallback
import numpy as np

from config import PPOConfig
from utils import ensure_dirs, set_global_seed


class StepRewardCallback(BaseCallback):
    def _on_step(self) -> bool:
        rewards = self.locals.get("rewards")
        if rewards is not None:
            self.logger.record("custom/step_reward", float(rewards[0]))
        return True


def main():
    cfg = PPOConfig()
    ensure_dirs(cfg.models_dir, cfg.logs_dir)
    set_global_seed(cfg.seed)

    def make_env():
        env = ParkOrRide()
        env = Monitor(env)
        return env

    learning_rates = [1e-4, 1e-3, 1e-2]

    for lr in learning_rates:
        # Recréer l'env à chaque run pour éviter les conflits entre modèles
        env_parallel = DummyVecEnv([make_env for _ in range(cfg.n_envs)])
        env_parallel = VecMonitor(env_parallel)

        model = PPO(
            "MlpPolicy",
            env_parallel,
            learning_rate=lr,
            n_steps=cfg.n_steps,
            batch_size=cfg.batch_size,
            gamma=cfg.gamma,
            gae_lambda=cfg.gae_lambda,
            clip_range=cfg.clip_range,
            ent_coef=cfg.ent_coef,
            verbose=1,
            tensorboard_log=str(cfg.logs_dir),
        )

        callback = StepRewardCallback()

        # tb_log_name inclut le lr → dossier : PPO_lr_0.0001_1, PPO_lr_0.001_1, etc.
        model.learn(
            total_timesteps=cfg.total_timesteps,
            tb_log_name=f"PPO_lr_{lr}",
            callback=callback,
        )

        model.save(f"{cfg.models_dir}/ppo_lr_{lr}")
        print(f"Modèle sauvegardé : ppo_lr_{lr}")

        env_parallel.close()


if __name__ == "__main__":
    main()