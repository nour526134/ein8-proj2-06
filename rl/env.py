import numpy as np
import random as rd
import gymnasium as gym
import parkingservice as ps
class parkorride(gym.Env):
    def __init__(self,car_simulator,train_service,parking_service,configurator):
        """"
        we define:
        0 as the action corresponding to ride 
        1 the action corrsponding to park
        """
        """
        The metrics are :
            those provided by train service:
                    dist_train_dest
                    train_dest_time 
                    next_train_wait_time
            those provided by car simulator :
                    dist_car_dest
                    dist_car_station
                    car_dest_time
                    traffic_rate     
                    car_time
            those provided by parking service:
                    parking_availability
        as for later we may consider adding walk time to parking and replace dist_car_station with dist_car_nearest_parking 
        for more precision




        """
        """
        for now :
            the parkorride module contains the simulator and trainservice and parkingservice and the configurator
        """
        self.truncated=False
        self.terminated=False
        self.conf=configurator
        self.sim=simulator
        self.ts=train_service
        self.ps=parking_service
        self.observation_space=gym.spaces.box(low=np.zeros(10),high=np.ones(10),dtype=np.float32)
        self.action_space=gym.Discrete(2)
        self.reward=0
        self.steps=0
        self.parking_availability=ps.initialise_parking_availability()
    def set_observation_space(self,params):
        self.observation_space.
    def reset(self):
        self.truncated=False
        self.terminated=False
        self.steps=0
        for i in range(self.cfg.max_iterations):
            self.steps+=1
            self.sim.advance(self.cfg.get_dt())
            if()        
    


    



