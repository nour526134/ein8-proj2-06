import math
import networkx as nx
import osmnx as ox

class ParkingServiceWalk:
    def __init__(self,parkings, walk_speed_kmh=5.0):
        self.Gw =ox.graph_from_place(
        "Paris, France",network_type="walk",simplify=True)
        self.G_walk = ox.utils_graph.get_undirected(self.G_walk)
        self.parkings = parkings
        self.walk_speed_kmh = walk_speed_kmh
        self._cache = {}

    def _nearest_walk_node(self, lat, lon):
        return ox.distance.nearest_nodes(self.Gw, X=lon, Y=lat)

    def closest_parking_to_station_walk(self, station_lat, station_lon, k=10):
        """
        Prend les k parkings “géographiquement” les plus proches,
        puis choisit celui qui minimise la distance piétonne réelle.
        """
        if not self.parkings:
            return None
        def approx_dist2(p):
            return (p["lat"] - station_lat) ** 2 + (p["lon"] - station_lon) ** 2
        candidates = sorted(self.parkings, key=approx_dist2)[:max(1, k)]
        s_node = self._nearest_walk_node(station_lat, station_lon)

        best = None
        best_len = float("inf")

        for p in candidates:
            p_node = self._nearest_walk_node(p["lat"], p["lon"])
            key = (p_node, s_node)

            if key in self._cache:
                length_m = self._cache[key]
            else:
                try:
                    length_m = nx.shortest_path_length(self.Gw, p_node, s_node, weight="length")
                except nx.NetworkXNoPath:
                    length_m = float("inf")
                self._cache[key] = length_m

            if length_m < best_len:
                best_len = length_m
                best = p

        return best

    def walk_time_min_parking_to_station(self, parking, station_lat, station_lon):
        if parking is None:
            return 0.0

        p_node = self._nearest_walk_node(parking["lat"], parking["lon"])
        s_node = self._nearest_walk_node(station_lat, station_lon)

        key = (p_node, s_node)
        if key in self._cache:
            length_m = self._cache[key]
        else:
            try:
                length_m = nx.shortest_path_length(self.Gw, p_node, s_node, weight="length")
            except nx.NetworkXNoPath:
                return 30.0  
            self._cache[key] = length_m

        dist_km = length_m / 1000.0
        return 60.0 * dist_km / max(self.walk_speed_kmh, 1e-6)