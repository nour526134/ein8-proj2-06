import math
import random
from datetime import datetime
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from src.osm.itinerary_manager import ItineraryManager
from src.gtfs_service import GTFSService
import networkx as nx


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
        self.gtfs_service = GTFSService("data/gtfs")
        stops_df = self.gtfs_service.load_stops()
        
        # Convertir en dictionnaire {stop_id: {'lat': ..., 'lon': ..., 'name': ...}}
        self.stations = {}
        for _, row in stops_df.iterrows():
            self.stations[row['stop_id']] = {
                'lat': row['stop_lat'],
                'lon': row['stop_lon'],
                'name': row['stop_name']
            }

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
        self.time_to_park=0.0
        self.dist_id=None
    def float_hour_to_hhmmss(self,hour_float):
        """
        Convertit un float (ex: 8.25) en string "HH:MM:SS"
        """
        h = int(hour_float)
        m = int((hour_float - h) * 60)
        s = int((((hour_float - h) * 60) - m) * 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    
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
        self.current_hour = self.rng.uniform(6.0, 20.0)

        # Choisir deux stations aléatoires
        start_station_id = self.rng.choice(list(self.stations.keys()))
        start_station = self.stations[start_station_id]
        
        current_time_str = self.float_hour_to_hhmmss(self.current_hour)
        reachable_stations = self.gtfs_service.get_reachable_stations(start_station_id, current_time_str)
        if reachable_stations.empty:
            raise RuntimeError(f"Aucune station accessible depuis {start_station_id}")
        dest_station_row = self.rng.choice(reachable_stations.to_dict(orient="records"))
        dest_station = {
        "id": dest_station_row["destination_station_id"],
        "lat": dest_station_row["destination_lat"],
        "lon": dest_station_row["destination_lon"],
        "name": dest_station_row["destination_station_name"]
        }
        self.dest_id=dest_station_row["destination_station_id"]
        # Position aléatoire proche de la station de départ
        station_node = self.router.nearest_node(start_station['lat'], start_station['lon'])
        nearby_nodes = self.router.nodes_within_radius(start_station['lat'], start_station['lon'], radius_km=0.5)
        if not nearby_nodes:
            nearby_nodes = [station_node]
        self.position_node = self.rng.choice(nearby_nodes)
        self.position_lat, self.position_lon = self.router.get_node_coords(self.position_node)

        # Calcul du chemin vers la destination
        self.path_nodes = self.router.shortest_path(
            self.position_lat, self.position_lon,
            dest_station["lat"], dest_station["lon"]
        )
        self.current_index = 0
        self.remaining_distance_km = self.router.path_distance_km(self.path_nodes)

        self.current_saturation = self.traffic_level(self.current_hour)

        # Nœud courant
        car_node = self.router.nearest_node(self.position_lat, self.position_lon)

        # Trouver la station la plus proche sur le graphe
        closest = start_station
        self.closest_station_id = start_station_id
        self.station_lat = closest["lat"]
        self.station_lon = closest["lon"]

        # Chemin vers la station la plus proche
        self.dest_path_nodes = self.router.shortest_path(
            self.position_lat, self.position_lon,
            self.station_lat, self.station_lon
        )
        self.dist_to_station_km = self.router.path_distance_km(self.dest_path_nodes)

    def car_time_to_parking(self,parking):
        speed = self.speed_kmh(self.current_saturation)
        path = self.router.shortest_path(
            self.position_lat, self.position_lon,
            parking["lat"], parking["lon"]
        )
        dist=self.router.path_distance_km(path)
        time_to_parking_min=60 * dist / max(speed , 1e-6)
        return time_to_parking_min



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
                distance_step = 0

        self.remaining_distance_km -= distance_traveled
        old_hour = self.current_hour
        self.current_hour += dt_min / 60
        if self.current_hour - old_hour > 0.5:
            self.current_saturation = self.traffic_level(self.current_hour)

   
    def get_metrics(self):
        return {
            "time_min": self.current_hour * 60,
            "distance_to_station_km": self.dist_to_station_km,
            "distance_to_dest_km": self.remaining_distance_km,
            "saturation": self.current_saturation,
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
        speed = self.speed_kmh(self.current_saturation)
        return 60 * self.remaining_distance_km / max(speed, 1e-6)
    


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