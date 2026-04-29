class Configurator:
    """
    Configuration parameters for the environment.
    """

    def __init__(
        self,
        max_iterations=10000,          # Max steps during reset to reach a station
        time_step_min=1.0,           # Δt for simulator advance (minutes)
        decision_distance_km=2.0,    # Threshold to consider "near a station"
        reward_factor=1.0,           # reward = -reward_factor * total_time
        max_dist_station_km=15.0,    # For observation normalization
        max_dist_dest_km=40.0,       # For observation normalization
        max_eta_min=120.0,
        max_wait_min=120.0,   # aligné avec le cap dans transit_realtime_service
        max_trip_min=120.0,   # TER Bordeaux peuvent durer jusqu'à 2h
        max_dist_parking_km=15,
        max_eta_car_parking=100,
        parking=0.1,
        traffic=0.3,
        realtime_refresh_sec=120
    ):
        self.max_iterations = max_iterations
        self.dt_min = time_step_min
        self.decision_distance_km = decision_distance_km
        self.reward_factor = reward_factor
        self.max_dist_station_km = max_dist_station_km
        self.max_dist_dest_km = max_dist_dest_km
        self.max_eta_min = max_eta_min
        self.max_wait_min = max_wait_min
        self.max_trip_min = max_trip_min
        self.max_dist_parking_km=max_dist_parking_km
        self.max_eta_car_parking=max_eta_car_parking
        self.traffic_factor=traffic
        self.parking_factor=parking
        self.realtime_refresh_sec=120

