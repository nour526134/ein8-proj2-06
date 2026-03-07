import math
import random
from datetime import datetime
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from src.osm.itinerary_manager import ItineraryManager
from src.gtfs_service import GTFSService
import networkx as nx
from typing import Dict, Any, Optional
import pandas as pd
import numpy as np

def haversine_m(lat1, lon1, lat2, lon2) -> float:
    """Distance Haversine en mètres."""
    R = 6371000.0
    phi1 = np.radians(lat1)
    phi2 = np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlambda = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(phi1) * np.cos(phi2) * np.sin(dlambda / 2) ** 2
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))
    return float(R * c)

class CarSimulator:
    """
    Simulateur de voiture réaliste sur graphe OSM
    Interface compatible PPO :
    - reset(seed=None)
    - advance(dt_min)
    - get_metrics()
    - get_dist_to_station_km()
    - get_closest_station_id()
    - get_time_min()
    - car_time_to_station()
    - car_time_to_dest()
    - get_dist_to_parking_km()
    -get_time_to_reach_parking()
    """

    def __init__(self, graphml_path="data/osm/bordeaux_network.graphml", v_max_kmh=50, v_min_kmh=10,
                 sigma=1.5, noise_amp=0.1, seed=None):
        self.v_max = v_max_kmh
        self.v_min = v_min_kmh
        self.sigma = sigma
        self.noise_amp = noise_amp
        self.rng = random.Random(seed)

        # Paramètres de trafic
        self.base = 0.25
        self.morning_peak = 0.45
        self.evening_peak = 0.50
        self.morning_hour = 8.0
        self.evening_hour = 17
        # Charger les stations GTFS
        self.gtfs_service = GTFSService("data/gtfs_bordeaux")
        self.stations =self.gtfs_service.load_stops()
        
       
        # Routeur OSM
        self.router = ItineraryManager(graphml_path)

        # État du véhicule
        self.current_hour = 8.0
        self.position_lat = None
        self.position_lon = None
        self.path_nodes = []
        self.current_index = 0
        self.closest_station_id = None
        self.station_lat = None
        self.station_lon = None
        self.remaining_distance_km = 0
        self.dist_to_station_km = 0
        self.current_saturation = 0
        self.dest_path_nodes = []
        self.dist_id=None
        self.dist=0.0
        self.total_car_time_to_dest_min=0.0
   
    
    def traffic_level(self, hour):
        """Niveau de saturation du trafic (0 à 1)"""
        morning = math.exp(-((hour - self.morning_hour) ** 2) / (2 * self.sigma ** 2))
        evening = math.exp(-((hour - self.evening_hour) ** 2) / (2 * self.sigma ** 2))
        mu = self.base + self.morning_peak * morning + self.evening_peak * evening
        noise = self.rng.uniform(-self.noise_amp, self.noise_amp)
        return max(0, min(mu + noise, 1))

    def speed_kmh(self, saturation):
        """Vitesse actuelle selon saturation"""
        return self.v_min + (1 - saturation) * (self.v_max - self.v_min)

    def reset(self, seed=None):
        if seed is not None:
            self.rng.seed(seed)

        MAX_RETRIES = 20
        for attempt in range(MAX_RETRIES):
            self.current_hour = self.rng.uniform(6.0, 20.0)

            start_station_id = self.rng.choice(list(self.stations.keys()))
            start_station = self.stations[start_station_id]

            reachable_stations = self.gtfs_service.get_reachable_stations(start_station_id)
            if reachable_stations.empty:
                continue

            dest_station_row = self.rng.choice(reachable_stations.to_dict(orient="records"))
            dest_station_id = dest_station_row["destination_station_id"]
            dest_station_lat = dest_station_row["destination_lat"]
            dest_station_lon = dest_station_row["destination_lon"]

            dest_node = self.router.nearest_node(dest_station_lat, dest_station_lon)
            dest_lat, dest_lon = self.router.get_node_coords(dest_node)
            #filtre fictif que je vais enleve quand on aura bien filtrer la data 
            
            if haversine_m(dest_station_lat, dest_station_lon, dest_lat, dest_lon) > 1000:
                continue
            start_snap_node = self.router.nearest_node(start_station['lat'], start_station['lon'])
            start_snap_lat, start_snap_lon = self.router.get_node_coords(start_snap_node)
            if haversine_m(start_station['lat'], start_station['lon'], start_snap_lat, start_snap_lon) > 1000:
                continue
            # fin 
            start_nearby = self.router.nodes_within_radius(
                start_station['lat'], start_station['lon'], radius_km=5.0
            )
            self.rng.shuffle(start_nearby)

            for candidate_node in start_nearby:
                candidate_lat, candidate_lon = self.router.get_node_coords(candidate_node)

                dist_to_start_station_m = haversine_m(
                    candidate_lat, candidate_lon,
                    start_station['lat'], start_station['lon']
                )
                if dist_to_start_station_m < 200:
                    continue

                dist_to_dest_station_m = haversine_m(
                    candidate_lat, candidate_lon,
                    dest_station_lat, dest_station_lon
                )
                if dist_to_dest_station_m < dist_to_start_station_m:
                    continue

                path_to_station = self.router.shortest_path(
                    candidate_lat, candidate_lon,
                    start_station['lat'], start_station['lon']
                )
                dist_to_station = self.router.path_distance_km(path_to_station)
                if dist_to_station < 0.2:
                    continue

                path = self.router.shortest_path(candidate_lat, candidate_lon, dest_lat, dest_lon)
                if path is None or len(path) < 2:
                    continue

                total_dist = self.router.path_distance_km(path)
                if total_dist < 0.5:
                    continue

                self.position_lat = candidate_lat
                self.position_lon = candidate_lon
                self.position_node = candidate_node
                self.path_nodes = path
                self.current_index = 0

                self.closest_station_id = start_station_id
                self.station_lat = start_station['lat']
                self.station_lon = start_station['lon']

                self.dest_id = dest_station_id
                self.dest_station_lat = dest_station_lat
                self.dest_station_lon = dest_station_lon

                self.dist = total_dist
                self.remaining_distance_km = total_dist
                self.dist_to_station_km = dist_to_station
                self.station_path_nodes = path_to_station

                self.current_saturation = self.traffic_level(self.current_hour)
                speed_at_start = self.speed_kmh(self.current_saturation)
                self.total_car_time_to_dest_min = 60 * total_dist / max(speed_at_start, 1e-6)
                return

        raise RuntimeError(f"Aucun chemin valide trouvé après {MAX_RETRIES} tentatives")

    def advance(self, dt_min):
        """Avance le véhicule le long du chemin"""
        speed = self.speed_kmh(self.current_saturation)
        distance_step = speed * dt_min / 60
        distance_traveled = 0

        while distance_step > 0 and self.current_index < len(self.path_nodes) - 1:
            n1 = self.path_nodes[self.current_index]
            n2 = self.path_nodes[self.current_index + 1]

            # longueur de l'arête
            d = self.router.get_edge_length_km(n1, n2)

            if distance_step >= d:
                self.current_index += 1
                self.position_lat, self.position_lon = self.router.get_node_coords(n2)
                distance_step -= d
                distance_traveled += d
            else:
                ratio = distance_step / d
                lat1, lon1 = self.router.get_node_coords(n1)
                lat2, lon2 = self.router.get_node_coords(n2)
                self.position_lat += ratio * (lat2 - lat1)
                self.position_lon += ratio * (lon2 - lon1)
                distance_traveled += distance_step
                distance_step = 0

        self.remaining_distance_km = max(0.0,self.remaining_distance_km - distance_traveled)
        old_hour = self.current_hour
        self.current_hour += dt_min / 60
        if self.current_hour - old_hour > 0.5:
            self.current_saturation = self.traffic_level(self.current_hour)

   
    def get_metrics(self):
        return {
            "time_min": self.current_hour * 60,
            "dist_to_station_km": self.dist_to_station_km,
            "dist_to_dest_km": self.remaining_distance_km,
            "traffic": self.current_saturation,
        }

    def get_dist_to_station_km(self):
        return self.dist_to_station_km

    def get_closest_station_id(self):
        return self.closest_station_id
    
    def get_dest_id(self):
        return self.dest_id
    
    def get_time_min(self):
        return self.current_hour * 60

    def car_time_to_station(self):
        speed = self.speed_kmh(self.current_saturation)
        return 60 * self.dist_to_station_km / max(speed, 1e-6)

    def car_time_to_dest(self):
        return self.total_car_time_to_dest_min
    
    def car_time_to_parking(self,parking):
        speed = self.speed_kmh(self.current_saturation)
        print("WAHAAVERSINE\n",haversine_m(self.position_lat, self.position_lon,parking["lat"], parking["lon"]))
        path = self.router.shortest_path(
            self.position_lat, self.position_lon,
            parking["lat"], parking["lon"]
        )
        dist=self.router.path_distance_km(path)
        if dist == float("inf"):
            dist=haversine_m(self.position_lat, self.position_lon,parking["lat"], parking["lon"])/1000

        time_to_parking_min=60 * dist / max(speed , 1e-6)
        return time_to_parking_min

    


if __name__ == "__main__":
    graph_path = "data/osm/bordeaux_network.graphml"

    sim = CarSimulator(graph_path)
    sim.reset(seed=42)

    print("Voiture initialisée")
    print(f"Position lat/lon : {sim.position_lat:.6f}, {sim.position_lon:.6f}")
    print(f"Closest station : {sim.get_closest_station_id()}")
    print(f"Distance à la station la plus proche : {sim.get_dist_to_station_km():.3f} km")
    print(f"Destination distance totale : {sim.remaining_distance_km:.3f} km")
    print(f"Trafic initial : {sim.current_saturation:.2f}")

    sim.advance(dt_min=5)
    print("\nAprès 5 minutes d'avance :")
    print(f"Position lat/lon : {sim.position_lat:.6f}, {sim.position_lon:.6f}")
    print(f"Distance restante : {sim.remaining_distance_km:.3f} km")
    print(f"Trafic : {sim.current_saturation:.2f}")