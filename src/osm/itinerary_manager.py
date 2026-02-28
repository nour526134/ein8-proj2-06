import osmnx as ox
import networkx as nx
from pathlib import Path


class ItineraryManager:
    """Gestionnaire réseau OSM"""

    def __init__(self, network_path="data/osm/bordeaux_network.graphml"):
        if not Path(network_path).exists():
            raise FileNotFoundError(f"Réseau non trouvé: {network_path}")

        print("Chargement du réseau...")
        self.G = ox.load_graphml(network_path)
        print(f"Réseau chargé: {len(self.G.nodes):,} nœuds")


    def nearest_node(self, lat, lon):
        return ox.distance.nearest_nodes(self.G, X=lon, Y=lat)

    def shortest_path(self, lat1, lon1, lat2, lon2):
        n1 = self.nearest_node(lat1, lon1)
        n2 = self.nearest_node(lat2, lon2)
        return nx.shortest_path(self.G, n1, n2, weight="length")

    def path_distance_km(self, path):
        return nx.path_weight(self.G, path, weight="length") / 1000

    def shortest_distance_km(self, lat1, lon1, lat2, lon2):
        path = self.shortest_path(lat1, lon1, lat2, lon2)
        return self.path_distance_km(path)

    def get_edge_length_km(self, node1, node2):
        """Longueur d'une arête en km"""
        edge_data = self.G.get_edge_data(node1, node2)
        edge = list(edge_data.values())[0]
        return edge["length"] / 1000

    def get_node_coords(self, node):
        """Retourne (lat, lon) d'un nœud"""
        data = self.G.nodes[node]
        return data["y"], data["x"]