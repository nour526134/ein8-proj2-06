
"""
Gestionnaire d'itinéraires avec OpenStreetMap
Version finale sans projection (utilise scikit-learn)
"""
import osmnx as ox
import networkx as nx
from geopy.distance import geodesic
from pathlib import Path

from websockets import route

class ItineraryManager:
    """Calcul d'itinéraires et distances avec OSM"""
    
    def __init__(self, network_path="data/osm/bordeaux_network.graphml"):
        print(" Chargement du réseau routier...")
        
        if Path(network_path).exists():
            #  SOLUTION FINALE: Ne PAS projeter, utiliser scikit-learn
            self.G = ox.load_graphml(network_path)
            print(f" Réseau chargé: {len(self.G.nodes):,} nœuds, {len(self.G.edges):,} arêtes")
        else:
            raise FileNotFoundError(
                f"Réseau non trouvé: {network_path}\n"
                "Exécutez: python scripts/download_osm_bordeaux.py"
            )
    
    def get_nearest_node(self, lat, lon):
        """Trouve le nœud le plus proche (utilise scikit-learn)"""
        return ox.distance.nearest_nodes(self.G, lon, lat)
    
    def calculate_route(self, start_lat, start_lon, end_lat, end_lon):
        """Calcule le plus court chemin"""
        try:
            start_node = self.get_nearest_node(start_lat, start_lon)
            end_node = self.get_nearest_node(end_lat, end_lon)
            
            # Calculer le chemin
            route = nx.shortest_path(self.G, start_node, end_node, weight='length')
            
            # Distance totale
            # Calcul manuel en itérant sur les arêtes
            distance_m = 0
            for i in range(len(route) - 1):
                u, v = route[i], route[i + 1]  # Nœuds consécutifs
                edge_data = self.G.get_edge_data(u, v)  # Données de l'arête
                distance_m += edge_data[0]['length']  # Longueur en mètres
            distance_km = distance_m / 1000
            
            # Durée estimée
            avg_speed_kmh = 40
            duration_minutes = (distance_km / avg_speed_kmh) * 60
            
            # Coordonnées du parcours
            route_coords = [(self.G.nodes[node]['y'], self.G.nodes[node]['x']) for node in route]
            
            return {
                'distance_km': round(distance_km, 2),
                'duration_minutes': round(duration_minutes, 1),
                'route_nodes': route,
                'route_coords': route_coords,
                'success': True
            }
            
        except nx.NetworkXNoPath:
            # Fallback: distance à vol d'oiseau
            crow_distance = geodesic((start_lat, start_lon), (end_lat, end_lon)).km
            
            return {
                'distance_km': round(crow_distance * 1.3, 2),
                'duration_minutes': round((crow_distance * 1.3 / 40) * 60, 1),
                'route_nodes': [],
                'route_coords': [],
                'success': False,
                'warning': 'Distance estimée (pas de chemin trouvé)'
            }
        except Exception as e:
            # Autre erreur
            print(f"Erreur lors du calcul: {e}")
            crow_distance = geodesic((start_lat, start_lon), (end_lat, end_lon)).km
            
            return {
                'distance_km': round(crow_distance * 1.3, 2),
                'duration_minutes': round((crow_distance * 1.3 / 40) * 60, 1),
                'route_nodes': [],
                'route_coords': [],
                'success': False,
                'warning': f'Erreur: {str(e)}'
            }
    
    def get_distance_to_station(self, current_lat, current_lon, station_lat, station_lon):
        """Distance routière jusqu'à une gare"""
        return self.calculate_route(current_lat, current_lon, station_lat, station_lon)['distance_km']
    
    def get_driving_time_to_station(self, current_lat, current_lon, station_lat, station_lon):
        """Temps de trajet jusqu'à une gare"""
        return self.calculate_route(current_lat, current_lon, station_lat, station_lon)['duration_minutes']
    
    def calculate_crow_distance(self, lat1, lon1, lat2, lon2):
        """Distance à vol d'oiseau"""
        return geodesic((lat1, lon1), (lat2, lon2)).km


if __name__ == "__main__":
    print("=" * 60)
    print(" TEST ITINERARY MANAGER")
    print("=" * 60)
    
    try:
        rm = ItineraryManager()
        
        # Mériadeck → Bordeaux Saint-Jean
        current = (44.8500, -0.5700)
        station = (44.8261, -0.5556)
        
        print(f"\nDépart: Mériadeck {current}")
        print(f"Arrivée: Bordeaux Saint-Jean {station}\n")
        
        route = rm.calculate_route(*current, *station)
        
        print(f" Distance: {route['distance_km']} km")
        print(f"  Durée: {route['duration_minutes']} min")
        print(f" Succès: {route['success']}")
        
        if not route['success']:
            print(f" {route.get('warning', '')}")
        
        # Test supplémentaire
        print("\n" + "=" * 60)
        print(" Test de plusieurs destinations")
        print("=" * 60 + "\n")
        
        locations = {
            "Chartrons": (44.8550, -0.5720),
            "Bastide": (44.8350, -0.5450),
            "Pessac": (44.8000, -0.6300)
        }
        
        for name, pos in locations.items():
            route = rm.calculate_route(*pos, *station)
            status = "ok" if route['success'] else "ko"
            print(f"{status} {name:<15} : {route['distance_km']:5.1f} km ({route['duration_minutes']:4.1f} min)")
        
        print("\n" + "**" * 30)
        print("  ITINERARY MANAGER OPÉRATIONNEL !")
        print("**" * 30)
        
    except FileNotFoundError as e:
        print(f"error {e}")
    except Exception as e:
        print(f" Erreur inattendue: {e}")
        import traceback
        traceback.print_exc()


