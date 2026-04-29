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
            self.logger.record("custom/step_reward", float(np.mean(rewards)))
        return True


def main():
    cfg = PPOConfig()
    ensure_dirs(cfg.models_dir, cfg.logs_dir)
    set_global_seed(cfg.seed)

    def make_env():
        env = ParkOrRide()
        env = Monitor(env)
        return env

    gammas = [0.90, 0.95, 0.99]

    for gamma in gammas:
        print(f"\n--- Entraînement gamma={gamma} ---")

        env_parallel = DummyVecEnv([make_env for _ in range(cfg.n_envs)])
        env_parallel = VecMonitor(env_parallel)

        model = PPO(
            "MlpPolicy",
            env_parallel,
            learning_rate=cfg.learning_rate,
            n_steps=cfg.n_steps,
            batch_size=cfg.batch_size,
            gamma=gamma,                     # ← valeur variable
            gae_lambda=cfg.gae_lambda,
            clip_range=cfg.clip_range,
            ent_coef=cfg.ent_coef,
            verbose=1,
            tensorboard_log=str(cfg.logs_dir),
        )

        callback = StepRewardCallback()

        # tb_log_name → dossier : PPO_gamma_0.9_1, PPO_gamma_0.95_1, etc.
        model.learn(
            total_timesteps=cfg.total_timesteps,
            tb_log_name=f"PPO_gamma_{gamma}",
            callback=callback,
        )

        model.save(f"{cfg.models_dir}/ppo_gamma_{gamma}")
        print(f"Modèle sauvegardé : ppo_gamma_{gamma}")

        env_parallel.close()


if __name__ == "__main__":
    main()