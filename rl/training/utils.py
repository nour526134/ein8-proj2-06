
import os
import random
import numpy as np


def ensure_dirs(models_dir: str, logs_dir: str) -> None:
    os.makedirs(models_dir, exist_ok=True)
    os.makedirs(logs_dir, exist_ok=True)


def set_global_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    try:
        import torch
        torch.manual_seed(seed)#seed aussi torch si dispo
    except ImportError:
        pass