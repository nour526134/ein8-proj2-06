import sys
from pathlib import Path
import shutil
import json

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from rl.env.park_ride_env import ParkOrRide
from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv, VecMonitor
from stable_baselines3.common.monitor import Monitor
from stable_baselines3.common.callbacks import BaseCallback

from config import PPOConfig
from utils import ensure_dirs, set_global_seed


class StepRewardCallback(BaseCallback):
    def __init__(self):
        super().__init__()
        self.all_rewards = []

    def _on_step(self) -> bool:
        rewards = self.locals.get("rewards")
        if rewards is not None:
            self.all_rewards.append((self.num_timesteps, float(rewards[0])))
        return True


def main():
    cfg = PPOConfig()
    ensure_dirs(cfg.models_dir, cfg.logs_dir)
    set_global_seed(cfg.seed)

    def make_env():
        env = ParkOrRide()
        env = Monitor(env)
        return env

    gammas = [0.9, 0.99, 0.999]

    rewards_dir = Path("rewards_data_gamma")
    rewards_dir.mkdir(exist_ok=True)

    for gamma in gammas:
        gamma_log_dir = Path(cfg.logs_dir) / f"PPO_gamma_{gamma}_1"
        if gamma_log_dir.exists():
            shutil.rmtree(gamma_log_dir)
            print(f"Ancien log supprimé : {gamma_log_dir}")

        env_parallel = DummyVecEnv([make_env for _ in range(cfg.n_envs)])
        env_parallel = VecMonitor(env_parallel)

        model = PPO(
            "MlpPolicy",
            env_parallel,
            learning_rate=cfg.learning_rate,
            n_steps=cfg.n_steps,
            batch_size=cfg.batch_size,
            gamma=gamma,
            gae_lambda=cfg.gae_lambda,
            clip_range=cfg.clip_range,
            ent_coef=cfg.ent_coef,
            verbose=1,
            tensorboard_log=str(cfg.logs_dir),
        )

        callback = StepRewardCallback()
        model.learn(
            total_timesteps=cfg.total_timesteps,
            tb_log_name=f"PPO_gamma_{gamma}",
            callback=callback,
        )

        save_path = rewards_dir / f"rewards_gamma_{gamma}.json"
        with open(save_path, "w") as f:
            json.dump(callback.all_rewards, f)
        print(f"Rewards sauvegardées : {save_path} ({len(callback.all_rewards)} steps)")

        model.save(f"{cfg.models_dir}/ppo_gamma_{gamma}")
        print(f"Modèle sauvegardé : ppo_gamma_{gamma}")
        env_parallel.close()


if __name__ == "__main__":
    main()
