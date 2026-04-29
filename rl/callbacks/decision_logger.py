import os
import csv
from stable_baselines3.common.callbacks import BaseCallback


class DecisionLoggerCallback(BaseCallback):
    def __init__(self, log_path="logs/decision_log.csv", verbose=0):
        super().__init__(verbose)
        self.log_path = log_path

        os.makedirs(os.path.dirname(log_path), exist_ok=True)

        with open(self.log_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "step",
                "action_pred",
                "action_opt",
                "reward",
                "TP",
                "FP",
                "FN",
                "TN"
            ])

        self.TP = 0
        self.FP = 0
        self.FN = 0
        self.TN = 0

    def _optimal_action(self, info):
        car = info.get("car_dest_time", 0)
        train = (
            info.get("car_parking_time", 0)
            + info.get("walk_time", 0)
            + info.get("train_wait_min", 0)
            + info.get("train_trip_min", 0)
        )
        parking_id = info.get("parking_id")
        if parking_id is None:
            return 0
        return 0 if car <= train else 1

    def _on_step(self) -> bool:
        infos = self.locals["infos"]
        actions = self.locals["actions"]
        rewards = self.locals["rewards"]

        info = infos[0]
        action_pred = int(actions[0])
        # Ignorer les épisodes truncated ou invalides
        if info.get("done_reason") not in ("decision_made", "no_parking"):
            return True
        reward = float(rewards[0])

        action_opt = self._optimal_action(info)

        if action_pred == 1 and action_opt == 1:
            self.TP += 1
        elif action_pred == 1 and action_opt == 0:
            self.FP += 1
        elif action_pred == 0 and action_opt == 1:
            self.FN += 1
        else:
            self.TN += 1

        step = self.num_timesteps

        with open(self.log_path, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                step,
                action_pred,
                action_opt,
                reward,
                self.TP,
                self.FP,
                self.FN,
                self.TN
            ])

        return True