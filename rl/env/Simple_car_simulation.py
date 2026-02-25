import math
import random
import csv
import osmnx as ox
import networkx as nx


def distance_km(lat1, lon1, lat2, lon2):
    """Distance orthodromique (Haversine) entre deux points GPS"""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a =math.sin(dlat / 2)**2+math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(dlon / 2)**2
    c = 2*math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R*c





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
        self.morning_hour = 8.0
        self.evening_hour = 17.5

        # j'ai besoin de cette fonction menal qui me donne un dictionnaire de station avec leur id lon lat 
        self.stations = load_stops()

        self.G = ox.graph_from_file(osm_path, simplify=True)

        self.current_hour = 8.0
        self.position_lat = None
        self.position_lon = None
        self.path_nodes = []  
        self.current_index = 0
        self.closest_station_id = None
        self.station_lat = None
        self.station_lon = None
        self.remaining_distance_km = 0.0
        self.dist_to_station_km = 0.0
        self.current_saturation = 0.0

 
    def clamp(self, x, lo=0.0, hi=1.0):
        return max(lo, min(hi, x))

    def traffic_level(self, hour):
        """Niveau de saturation du trafic (0 à 1)"""
        morning = math.exp(-((hour-self.morning_hour) ** 2) / (2 * self.sigma ** 2))
        evening = math.exp(-((hour-self.evening_hour) ** 2) / (2 * self.sigma ** 2))
        mu = self.base + self.morning_peak*morning + self.evening_peak * evening
        noise = self.rng.uniform(-self.noise_amp, self.noise_amp)
        return self.clamp(mu + noise)

    def speed_kmh(self, saturation):
        """Vitesse actuelle selon saturation"""
        return self.v_min + (1.0-saturation)*(self.v_max - self.v_min)


    def nearest_node(self, lat, lon):
        """Retourne le noeud OSM le plus proche d'une position GPS"""
        return ox.distance.nearest_nodes(self.G, X=lon, Y=lat)

    def shortest_path(self, start_lat, start_lon, dest_lat, dest_lon):
        """Calcule le chemin le plus court entre deux positions GPS"""
        start_node = self.nearest_node(start_lat, start_lon)
        end_node = self.nearest_node(dest_lat, dest_lon)
        return nx.shortest_path(self.G, source=start_node, target=end_node, weight='length')

    def reset(self, seed=None):
        """Réinitialise la simulation et choisit un trajet réaliste"""
        if seed is not None:
            self.rng.seed(seed)
        self.current_hour = 8.0

        start_station=self.rng.choice(self.stations)
        dest_station=self.rng.choice([s for s in self.stations if s != start_station])

        self.position_lat=start_station["lat"]+self.rng.uniform(-0.001, 0.001)
        self.position_lon=start_station["lon"]+self.rng.uniform(-0.001, 0.001)

        self.path_nodes = self.shortest_path(
            self.position_lat, self.position_lon,
            dest_station["lat"], dest_station["lon"]
        )
        self.current_index = 0

        self.remaining_distance_km = sum(
            distance_km(
                self.G.nodes[self.path_nodes[i]]['y'], self.G.nodes[self.path_nodes[i]]['x'],
                self.G.nodes[self.path_nodes[i+1]]['y'], self.G.nodes[self.path_nodes[i+1]]['x']
            )
            for i in range(len(self.path_nodes)-1)
        )

        self.current_saturation=self.traffic_level(self.current_hour)
        closest = min(
            self.stations,
            key=lambda s: distance_km(self.position_lat, self.position_lon, s["lat"], s["lon"])
        )
        self.closest_station_id=closest["id"]
        self.station_lat=closest["lat"]
        self.station_lon=closest["lon"]
        self.dist_to_station_km=distance_km(
            self.position_lat, self.position_lon,
            closest["lat"], closest["lon"]
        )


    def advance(self, dt_min):
        """Avance le long du chemin OSM pendant dt_min minutes"""
        speed = self.speed_kmh(self.current_saturation)
        distance_step = speed*dt_min / 60.0  # km

        while distance_step > 0 and self.current_index < len(self.path_nodes)-1:
            n1 = self.path_nodes[self.current_index]
            n2 = self.path_nodes[self.current_index + 1]
            d = distance_km(
                self.G.nodes[n1]['y'], self.G.nodes[n1]['x'],
                self.G.nodes[n2]['y'], self.G.nodes[n2]['x']
            )
            if distance_step >= d:
                self.current_index+= 1
                self.position_lat=self.G.nodes[n2]['y']
                self.position_lon=self.G.nodes[n2]['x']
                distance_step -=d
            else:
                ratio = distance_step/d
                self.position_lat +=ratio*(self.G.nodes[n2]['y'] - self.G.nodes[n1]['y'])
                self.position_lon +=ratio*(self.G.nodes[n2]['x'] - self.G.nodes[n1]['x'])
                distance_step = 0

        self.remaining_distance_km = sum(
            distance_km(
                self.G.nodes[self.path_nodes[i]]['y'], self.G.nodes[self.path_nodes[i]]['x'],
                self.G.nodes[self.path_nodes[i+1]]['y'], self.G.nodes[self.path_nodes[i+1]]['x']
            )
            for i in range(self.current_index, len(self.path_nodes)-1)
        )

        self.current_hour += dt_min / 60.0
        self.current_saturation = self.traffic_level(self.current_hour)


    def get_metrics(self):
        return {
            "time_min": self.current_hour*60,
            "distance_to_station_km": self.dist_to_station_km,
            "distance_to_dest_km": self.remaining_distance_km,
            "saturation": self.current_saturation,
        }

    def get_dist_to_station_km(self):
        return self.dist_to_station_km

    def get_closest_station_id(self):
        return self.closest_station_id

    def get_time_min(self):
        return self.current_hour*60

    def car_time_to_station(self):
        speed = self.speed_kmh(self.current_saturation)
        return 60.0*self.dist_to_station_km /max(speed, 1e-6)

    def car_time_to_dest(self):
        speed = self.speed_kmh(self.current_saturation)
        return 60.0*self.remaining_distance_km / max(speed, 1e-6)