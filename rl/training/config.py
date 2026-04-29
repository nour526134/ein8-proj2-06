from dataclasses import dataclass


@dataclass
class PPOConfig:
    seed:int = 42
    total_timesteps:int =100000
    n_envs:int= 1
    learning_rate: float = 3e-4 
    n_steps:int = 2048 # dans chaque env
    batch_size:int =64
    gamma : float =0.99
    gae_lambda: float = 0.95# estimation plus stable
    clip_range: float = 0.2 #limite le changement à±20%
    ent_coef: float = 0.01 # on change apres !!!!!!
    model_name: str = "ppo_modal_decision"
    models_dir: str = "models"
    logs_dir: str = "logs"
    save_freq: int = 20_000 #TOUS 20 000 steps, on crée fichier modèle intermédiaire






