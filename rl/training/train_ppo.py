
from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv

from rl.training.config import PPOConfig
from rl.training.utils import ensure_dirs, set_global_seed
from rl.simulators.car_simulator import CarSimulator  #a modifier par aiche si incorrect
from src.gtfs_service import GTFSService 
from rl.env.cfg import Configurator
import sys 
from pathlib import Path 

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.gtfs_service import GTFSService 

# cette ligne peut etre changer!!!
from rl.env.park_ride_env import ParkOrRide


def main():

    graph_path = "data/osm/bordeaux_network.graphml"
    car_sim = CarSimulator(graph_path) 
    train_svc = GTFSService("data/gtfs")
    config = Configurator()
    env = ParkOrRide(car_sim,train_svc,config)
    ensure_dirs(cfg.models_dir, cfg.logs_dir)
    set_global_seed(cfg.seed)
    env_parallel = DummyVecEnv([lambda: env for _ in range(cfg.n_envs)]) #DummyVecEnv prend liste de fcts

    model = PPO(
        "MlpPolicy", #réseau de neurones Multi-Layer Perceptron adapté aux vecteurs numériques
        env_parallel,
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