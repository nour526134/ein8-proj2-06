
from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv

from rl.training.config import PPOConfig
from rl.training.utils import ensure_dirs, set_global_seed

# cette ligne peut etre changer!!!
from rl.env.modal_env import ModalShiftEnv


def main():

    cfg = PPOConfig()
    ensure_dirs(cfg.models_dir, cfg.logs_dir)
    set_global_seed(cfg.seed)
    env = DummyVecEnv([lambda: ModalShiftEnv() for _ in range(cfg.n_envs)]) #DummyVecEnv prend liste de fcts

    model = PPO(
        "MlpPolicy", #réseau de neurones Multi-Layer Perceptron adapté aux vecteurs numériques
        env,
        learning_rate=cfg.learning_rate,
        n_steps=cfg.n_steps,
        batch_size=cfg.batch_size,
        gamma=cfg.gamma,
        gae_lambda=cfg.gae_lambda,
        clip_range=cfg.clip_range,
        ent_coef=cfg.ent_coef,
        verbose=1,
        tensorboard_log=cfg.logs_dir, #permet de voir Les courbes
    )

    model.learn(total_timesteps=cfg.total_timesteps)

    model.save(f"{cfg.models_dir}/{cfg.model_name}") # le f-string c est maniere d inserer variables!!!


if __name__ == "__main__":
    main()