
import numpy as np


def compute_decision_metrics(car_time: float, train_time: float, action: int) -> dict:

    best_time = min(car_time, train_time)

    if action == 0:
        chosen_time = car_time
    else:
        chosen_time = train_time

    correct = (chosen_time == best_time)
    regret = chosen_time - best_time 

    return {
        "correct": bool(correct),
        "regret": float(regret),
        "best_time": float(best_time),
        "chosen_time": float(chosen_time),
    }


def summarize_metrics(correct_list: list[bool], regret_list: list[float]) -> dict:
    correct_arr = np.array(correct_list, dtype=np.float32)
    regret_arr = np.array(regret_list, dtype=np.float32)

    return {
        "accuracy": float(correct_arr.mean()),           
        "mean_regret": float(regret_arr.mean()),       
        "max_regret": float(regret_arr.max()),        
    }