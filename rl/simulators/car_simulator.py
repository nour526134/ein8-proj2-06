import math
import random
import csv
import osmnx as ox
import networkx as nx
import sys 
from pathlib import Path 

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.gtfs_service import GTFSService

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
    """

    def __init__(self, osm_path, v_max_kmh=50.0, v_min_kmh=10.0,
                 sigma=1.5, noise_amp=0.1, seed=None):
        self.v_max = v_max_kmh
        self.v_min = v_min_kmh
        self.sigma = sigma
        self.noise_amp = noise_amp
        self.rng = random.Random(seed)

        self.base = 0.25
        self.morning_peak = 0.45
        self.evening_peak = 0.50
        self.morning_hour = 8
        self.evening_hour = 17

        # Charger les stations GTFS
        gtfs_service = GTFSService("data/gtfs")
        stops_df = gtfs_service.load_stops(stop_areas_only=True)
        
        # Convertir en dictionnaire {stop_id: {'lat': ..., 'lon': ..., 'name': ...}}
        self.stations = {}
        for _, row in stops_df.iterrows():
            self.stations[row['stop_id']] = {
                'lat': row['lat'],
                'lon': row['lon'],
                'name': row['stop_name']
            }

        self.G = ox.graph_from_xml(osm_path, simplify=True)

        self.current_hour = 8
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

    def traffic_level(self, hour):
        morning = math.exp(-((hour - self.morning_hour) ** 2) / (2 * self.sigma ** 2))
        evening = math.exp(-((hour - self.evening_hour) ** 2) / (2 * self.sigma ** 2))
        mu = self.base + self.morning_peak * morning + self.evening_peak * evening
        noise = self.rng.uniform(-self.noise_amp, self.noise_amp)
        return max(0, (min(mu + noise), 1))

    def speed_kmh(self, saturation):
        return self.v_min + (1 - saturation) * (self.v_max - self.v_min)

    def nearest_node(self, lat, lon):
        return ox.distance.nearest_nodes(self.G, X=lon, Y=lat)

    def shortest_path(self, start_lat, start_lon, dest_lat, dest_lon):
        start_node = self.nearest_node(start_lat, start_lon)
        end_node = self.nearest_node(dest_lat, dest_lon)
        return nx.shortest_path(self.G, source=start_node, target=end_node, weight='length')

    def reset(self, seed=None):
        if seed is not None:
            self.rng.seed(seed)
        self.current_hour = 8

        start_station = self.rng.choice(self.stations)
        dest_station = self.rng.choice([s for s in self.stations if s != start_station])

        self.position_lat = start_station["lat"] + self.rng.uniform(-0.001, 0.001)
        self.position_lon = start_station["lon"] + self.rng.uniform(-0.001, 0.001)

        self.path_nodes = self.shortest_path(
            self.position_lat,
            self.position_lon,
            dest_station["lat"],
            dest_station["lon"]
        )
        self.current_index = 0

        self.remaining_distance_km = nx.path_weight(
            self.G, self.path_nodes, weight="length"
        ) / 1000

        self.current_saturation = self.traffic_level(self.current_hour)

        car_node = self.nearest_node(self.position_lat, self.position_lon)

        closest = min(
            self.stations,
            key=lambda s: nx.shortest_path_length(
                self.G,
                car_node,
                self.nearest_node(s["lat"], s["lon"]),
                weight="length"
            )
        )

        self.closest_station_id = closest["id"]
        self.station_lat = closest["lat"]
        self.station_lon = closest["lon"]

        self.dest_path_nodes = self.shortest_path(
            self.position_lat,
            self.position_lon,
            closest["lat"],
            closest["lon"]
        )

        self.dist_to_station_km = nx.path_weight(
            self.G,
            self.dest_path_nodes,
            weigth="length"
        ) / 1000

    def advance(self, dt_min):
        speed = self.speed_kmh(self.current_saturation)
        distance_step = speed * dt_min / 60
        distance_traveled = 0

        while distance_step > 0 and self.current_index < len(self.path_nodes) - 1:
            n1 = self.path_nodes[self.current_index]
            n2 = self.path_nodes[self.current_index + 1]
            edge_data = self.G.get_edge_data(n1, n2)
            d = edge_data[0]["length"] / 1000

            if distance_step >= d:
                self.current_index += 1
                self.position_lat = self.G.nodes[n2]['y']
                self.position_lon = self.G.nodes[n2]['x']
                distance_step -= d
                distance_traveled += d
            else:
                ratio = distance_step / d
                self.position_lat += ratio * (self.G.nodes[n2]['y'] - self.G.nodes[n1]['y'])
                self.position_lon += ratio * (self.G.nodes[n2]['x'] - self.G.nodes[n1]['x'])
                distance_step = 0

        self.remaining_distance_km -= distance_traveled
        time = self.current_hour
        self.current_hour += dt_min / 60

        if self.current_hour - time > 0.5:
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

    def get_time_min(self):
        return self.current_hour * 60

    def car_time_to_station(self):
        speed = self.speed_kmh(self.current_saturation)
        return 60 * self.dist_to_station_km / max(speed, 1e-6)

    def car_time_to_dest(self):
        speed = self.speed_kmh(self.current_saturation)
        return 60 * self.remaining_distance_km / max(speed, 1e-6)