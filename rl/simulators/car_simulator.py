import math
import random
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from src.osm.itinerary_manager import ItineraryManager
from src.gtfs_service import GTFSService
import networkx as nx
from typing import Dict, Any, Optional
import pandas as pd
import numpy as np
import datetime

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

    def __init__(self, graphml_path=None, v_max_kmh=50, v_min_kmh=10,
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
        self.parking = None
        # Charger les stations GTFS
        self.gtfs_service = GTFSService()
        self.stations =self.gtfs_service.load_stops()
        
       
        # Routeur OSM
        self.router = ItineraryManager()

        # État du véhicule
        self.current_hour = 8.0
        self.position_lat = None
        self.position_lon = None
        self.current_index = 0
        self.closest_station_id = None
        self.station_lat = None
        self.station_lon = None
        self.remaining_distance_km = 0
        self.current_saturation = 0
        self.dest_path_nodes = []
        self.dist_id=None
        self.dist=0.0
        self.total_car_time_to_dest_min=0.0
        self.time_to_station=0.0
    
    def find_k_closest_stations(self,lat: float, lon: float, k: int = 1):
        distances = []
        for sid, sdata in self.stations.items():
            dist = haversine_m(lat, lon, sdata["lat"], sdata["lon"]) / 1000.0
            distances.append((sid, dist))
        distances.sort(key=lambda x: x[1])

        return distances[:k]
    
    def compute_average_traffic(self, total_time_min: float, step_min: float = 1.0) -> float:
        if total_time_min <= 0:
            return self.current_saturation

        t = self.current_hour
        total = 0.0
        n = 0

        time_elapsed = 0.0

        while time_elapsed < total_time_min:
            traffic = self.traffic_level(t)
            total += traffic
            n += 1

            t += step_min / 60.0
            time_elapsed += step_min

        return total / max(n, 1)
    
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

    def reset(self, seed=None, k_stations=1):
        if seed is not None:
            self.rng.seed(seed)
        MAX_RETRIES = 20
        all_nodes = list(self.router.G.nodes())
        for attempt in range(MAX_RETRIES):
            # 70% du temps : heure de pointe (P&R pertinent)
            # 30% du temps : heure creuse (voiture clairement meilleure)
            if self.rng.random() < 0.7:
                # Heure de pointe matin ou soir
                if self.rng.random() < 0.5:
                    self.current_hour = self.rng.uniform(7.0, 9.0)
                else:
                    self.current_hour = self.rng.uniform(16.0, 19.0)
            else:
                self.current_hour = self.rng.uniform(6.0, 21.0)
            candidate_node = self.rng.choice(all_nodes)
            candidate_lat, candidate_lon = self.router.get_node_coords(candidate_node)

            k_closest = self.find_k_closest_stations(candidate_lat, candidate_lon, k=k_stations)
            self.k_stations = []
            for sid, _ in k_closest:
                sdata = self.stations[sid]
                station_node = self.router.nearest_node(sdata["lat"], sdata["lon"])
                path = self.router.shortest_path_nodes(candidate_node, station_node)
                road_dist = self.router.path_distance_km(path)
                self.k_stations.append({
                    "id": sid, "lat": sdata["lat"], "lon": sdata["lon"],
                    "dist_km": road_dist, "path": path, "node": station_node,
                })

            self.k_stations.sort(key=lambda x: x["dist_km"])
            best = self.k_stations[0]

            if best["dist_km"] < 0.2:
                continue

            reachable = self.gtfs_service.get_reachable_stations(best["id"])
            if reachable.empty:
                continue

            
            reachable_records = reachable.to_dict(orient="records")
            far_destinations = [
                r for r in reachable_records
                if self.gtfs_service.train_trip_time(best["id"], r["destination_station_id"]) >= 15.0
            ]
            if not far_destinations:
                continue 
            dest_row = self.rng.choice(far_destinations)
            dest_node = self.router.nearest_node(dest_row["destination_lat"], dest_row["destination_lon"])
            dest_lat, dest_lon = self.router.get_node_coords(dest_node)

            dist_candidate_to_station = haversine_m(candidate_lat, candidate_lon, best["lat"], best["lon"])
            dist_candidate_to_dest = haversine_m(candidate_lat, candidate_lon, dest_lat, dest_lon)
            dist_station_to_dest = haversine_m(best["lat"], best["lon"], dest_lat, dest_lon)

            if dist_candidate_to_dest < dist_candidate_to_station:
                continue
            if dist_station_to_dest > dist_candidate_to_dest:
                continue

            path_to_dest = self.router.shortest_path_nodes(candidate_node, dest_node)
            if path_to_dest is None or len(path_to_dest) < 2:
                continue
            total_dist = self.router.path_distance_km(path_to_dest)
            if total_dist < 0.5:
                continue

            # Filtre : P&R n'a de sens que si le trajet voiture est assez long
            # pour qu'une attente train soit compétitive
            speed_now = self.speed_kmh(self.traffic_level(self.current_hour))
            est_car_time = 60.0 * total_dist / max(speed_now, 1e-6)
            if est_car_time < 20.0:  # ← moins de 20 min en voiture = P&R inutile
                continue

            self.position_lat = candidate_lat
            self.position_lon = candidate_lon
            self.position_node = candidate_node
            self.current_index = 0
            self.closest_station_id = best["id"]
            print(self.closest_station_id)
            print(self.current_hour)
            self.station_lat = best["lat"]
            self.station_lon = best["lon"]
            self.station = {"id": best["id"], "lat": best["lat"], "lon": best["lon"]}
            self.station_path_nodes = best["path"]
            self.dest_id = dest_row["destination_station_id"]
            self.dest_station_lat = dest_lat
            self.dest_station_lon = dest_lon
            self.dist = total_dist
            self.remaining_distance_km = best["dist_km"]
            self.current_saturation = self.traffic_level(self.current_hour)
            speed_at_start = self.speed_kmh(self.current_saturation)
            self.total_car_time_to_dest_min = 60 * total_dist / max(speed_at_start, 1e-6)
            self.time_to_station = 60 * best["dist_km"] / max(speed_at_start, 1e-6)
            return
        self.current_hour = 12.0
        start_station_id = next(iter(self.stations))
        start_station = self.stations[start_station_id]

        self.position_lat = start_station['lat']
        self.position_lon = start_station['lon']
        self.position_node = self.router.nearest_node(self.position_lat, self.position_lon)
        self.current_index = 0

        self.closest_station_id = start_station_id
        self.station_lat = start_station['lat']
        self.station_lon = start_station['lon']

        self.dest_id = start_station_id
        self.dest_station_lat = start_station['lat']
        self.dest_station_lon = start_station['lon']

        self.dist = 1.0
        self.remaining_distance_km = 0.5
        self.station_path_nodes = []

        self.current_saturation = self.traffic_level(self.current_hour)
        speed_at_start = self.speed_kmh(self.current_saturation)
        self.total_car_time_to_dest_min = 1.0
        self.time_to_station = 1.0

    def snapshot(self):
        return {
            "position_lat": self.position_lat,
            "position_lon": self.position_lon,
            "current_hour": self.current_hour,
            "current_saturation": self.current_saturation,
            "current_index": self.current_index,
            "station_path_nodes": self.station_path_nodes,
            "remaining_distance_km": self.remaining_distance_km,
            "time_to_station": self.time_to_station,
            "dist": self.dist,
            "closest_station_id": self.closest_station_id,
            "station_lat": self.station_lat,
            "station_lon": self.station_lon,
            "station": self.station,
        }
    def restore(self, snap):
        for k, v in snap.items():
            setattr(self, k, v)
    def load_station(self, station):
        current_node = self.router.nearest_node(self.position_lat, self.position_lon)
        next_node = station["node"]
        path = self.router.shortest_path_nodes(current_node, next_node)
        road_dist = self.router.path_distance_km(path)

        self.station_path_nodes = path
        self.current_index = 0
        self.closest_station_id = station["id"]
        self.station_lat = station["lat"]
        self.station_lon = station["lon"]
        self.station = {"id": station["id"], "lat": station["lat"], "lon": station["lon"]}
        self.remaining_distance_km = road_dist

        speed = self.speed_kmh(self.current_saturation)
        self.time_to_station = 60 * road_dist / max(speed, 1e-6)
    
    def simulate_to_station(self, station, dt_min) -> dict:
        snap = self.snapshot()
        self.load_station(station)

        for _ in range(self.cfg.max_iterations):
            self.advance(dt_min)
            if self.remaining_distance_km <= self.cfg.decision_distance_km:
                result = {
                    "station_id": station["id"],
                    "time_elapsed_min": (self.current_hour - snap["current_hour"]) * 60,
                    "dist_to_dest_km": self.dist,
                }
                self._restore(snap)
                return result

        self.restore(snap)
        return None

    def advance(self, dt_min):
        """Avance le véhicule le long du chemin"""
        speed = self.speed_kmh(self.current_saturation)
        distance_step = speed * dt_min / 60
        distance_traveled = 0

        while distance_step > 0 and self.current_index < len(self.station_path_nodes) - 1:
            n1 = self.station_path_nodes[self.current_index]
            n2 = self.station_path_nodes[self.current_index + 1]
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
                self.position_lat =lat1 +  ratio * (lat2 - lat1)
                self.position_lon =lon1 +  ratio * (lon2 - lon1)
                distance_traveled += distance_step
                distance_step = 0

        self.remaining_distance_km = max(0.0,self.remaining_distance_km - distance_traveled)
        self.dist = haversine_m(self.position_lat, self.position_lon,self.dest_station_lat, self.dest_station_lon)/1000
        if self.parking is not None:
            self.dist_to_parking_km = haversine_m(
                self.position_lat, self.position_lon,
                self.parking["lat"], self.parking["lon"]
            ) / 1000.0
            self.time_to_parking_min = 60 * self.dist_to_parking_km / max(speed, 1e-6)
        old_hour = self.current_hour
        self.current_hour += dt_min / 60
        self.time_to_station = max(0.0, self.time_to_station - dt_min)  
        if self.current_hour - old_hour > 0.5:
            self.current_saturation = self.traffic_level(self.current_hour)

        speed = self.speed_kmh(self.current_saturation)
        # Estimation prudente : moyenne entre vitesse actuelle et vitesse dans 30 min
        future_hour = self.current_hour + 0.5
        future_saturation = self.traffic_level(future_hour)
        future_speed = self.speed_kmh(future_saturation)
        avg_speed = (speed + future_speed) / 2.0
        self.total_car_time_to_dest_min = 60.0 * self.dist / max(avg_speed, 1e-6)
        
   
    def get_metrics(self):
        return {
            "time_min": self.current_hour * 60,
            "dist_to_station_km": self.remaining_distance_km,
            "dist_to_dest_km": self.dist,
            "dist_to_parking_km": getattr(self, "dist_to_parking_km", 0.0),  
            "traffic": self.current_saturation,
        }
        
    def get_dist_to_station_km(self):
        return self.remaining_distance_km

    def get_closest_station(self):
        return self.station
    
    def distance_to(self, lat: float, lon: float) -> float:
        """Distance routière en km depuis la position courante vers (lat, lon)."""
        try:
            path = self.router.shortest_path_nodes(
                self.router.nearest_node(self.position_lat, self.position_lon),
                self.router.nearest_node(lat, lon)
            )
            return self.router.path_distance_km(path)
        except Exception:
            return haversine_m(self.position_lat, self.position_lon, lat, lon) / 1000.0
    
    def get_dest_id(self):
        return self.dest_id
    
    def get_time_min(self):
        return self.current_hour * 60

    def car_time_to_station(self):
        return self.time_to_station

    def car_time_to_dest(self):
        return self.total_car_time_to_dest_min
    
    def get_k_stations(self):
        return self.k_stations

    def car_time_to_parking(self, parking):
        speed = self.speed_kmh(self.current_saturation)
        try:
            path = self.router.shortest_path_nodes(
                self.router.nearest_node(self.position_lat, self.position_lon),
                self.router.nearest_node(parking["lat"], parking["lon"])
            )
            dist = self.router.path_distance_km(path)
        except Exception:
            dist = float("inf")

        if dist == float("inf") or dist <= 0:
            dist = haversine_m(self.position_lat, self.position_lon,
                               parking["lat"], parking["lon"]) / 1000.0

        return 60.0 * dist / max(speed, 1e-6)
    


if __name__ == "__main__":
    graph_path = "data/osm/bordeaux_network.graphml"

    sim = CarSimulator(graph_path)
    sim.reset(seed=42)

    print("Voiture initialisée")
    print(f"Position lat/lon : {sim.position_lat:.6f}, {sim.position_lon:.6f}")
    print(f"Closest station : {sim.get_closest_station()}")
    print(f"Distance à la station la plus proche : {sim.get_dist_to_station_km():.3f} km")
    print(f"Destination distance totale : {sim.remaining_distance_km:.3f} km")
    print(f"Trafic initial : {sim.current_saturation:.2f}")

    sim.advance(dt_min=5)
    print("\nAprès 5 minutes d'avance :")
    print(f"Position lat/lon : {sim.position_lat:.6f}, {sim.position_lon:.6f}")
    print(f"Distance restante : {sim.remaining_distance_km:.3f} km")
    print(f"Trafic : {sim.current_saturation:.2f}")