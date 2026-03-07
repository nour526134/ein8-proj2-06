import osmnx as ox
import networkx as nx
import numpy as np
from scipy.spatial import KDTree
from pathlib import Path
from functools import lru_cache
import math

class ItineraryManager:
    """Gestionnaire réseau OSM optimisé pour PPO"""

    def __init__(self, network_path="data/osm/bordeaux_network.graphml"):
        if not Path(network_path).exists():
            raise FileNotFoundError(f"Réseau non trouvé: {network_path}")

        print("Chargement du réseau...")
        self.G = ox.load_graphml(network_path)
        print(f"Réseau chargé: {len(self.G.nodes):,} nœuds")

        largest_cc = max(nx.connected_components(self.G.to_undirected()), key=len)
        self.G = self.G.subgraph(largest_cc).copy()
        print(f"Graphe réduit: {len(self.G.nodes):,} nœuds")

        self.node_ids = list(self.G.nodes)
        coords = np.array([
            [self.G.nodes[n]['y'], self.G.nodes[n]['x']]
            for n in self.node_ids
        ])
        self._kdtree = KDTree(coords)
        self._node_coords = {
            n: (self.G.nodes[n]['y'], self.G.nodes[n]['x'])
            for n in self.node_ids
        }
        print("Index spatial KDTree construit.")

        self.path_cache = {}


    def nearest_node(self, lat, lon):
        _, idx = self._kdtree.query([lat, lon])
        return self.node_ids[idx]

    
    def nodes_within_radius(self, lat, lon, radius_km=0.5):
        lat_deg = radius_km / 111.0
        lon_deg = radius_km / (111.0 * math.cos(math.radians(lat)))
        idxs = self._kdtree.query_ball_point([lat, lon], max(lat_deg, lon_deg))
        
        # Trier par distance réelle
        nodes = [self.node_ids[i] for i in idxs]
        nodes.sort(key=lambda n: (self._node_coords[n][0] - lat)**2 + (self._node_coords[n][1] - lon)**2)
        return nodes or [self.nearest_node(lat, lon)]


    def shortest_path(self, lat1, lon1, lat2, lon2):
        n1 = self.nearest_node(lat1, lon1)
        n2 = self.nearest_node(lat2, lon2)
        return self.shortest_path_nodes(n1, n2)

    def shortest_path_nodes(self, n1, n2):
        """Cache par paire de nœuds (pas de coordonnées flottantes)"""
        key = (n1, n2)
        if key not in self.path_cache:
            try:
                self.path_cache[key] = nx.shortest_path(
                    self.G, n1, n2, weight="length"
                )
            except nx.NetworkXNoPath:
                self.path_cache[key] = None
        return self.path_cache[key]


    def path_distance_km(self, path):
        if path is None:
            return float("inf")
        return nx.path_weight(self.G, path, weight="length") / 1000

    def shortest_distance_km(self, lat1, lon1, lat2, lon2):
        """Éviter d'appeler dans une boucle sur tous les nœuds"""
        return self.path_distance_km(self.shortest_path(lat1, lon1, lat2, lon2))


    def get_edge_length_km(self, node1, node2):
        edge_data = self.G.get_edge_data(node1, node2)
        return list(edge_data.values())[0]["length"] / 1000

    def get_node_coords(self, node):
        return self._node_coords[node]   