
"""
Gestionnaire des lignes et voyages (routes.csv, trips.csv)
"""
import pandas as pd

class RoutesTripsManager:
    """Gère les lignes de train et les voyages"""
    
    def __init__(self, gtfs_path):
        """
        Args:
            gtfs_path: Chemin vers le dossier GTFS
        """
        print(" Chargement des lignes et voyages...")
        
        self.routes = pd.read_csv(f"{gtfs_path}/routes.csv")
        self.trips = pd.read_csv(f"{gtfs_path}/trips.csv")
        
        print(f" {len(self.routes):,} lignes")
        print(f" {len(self.trips):,} voyages")
    
    def get_all_routes(self):
        """Retourne toutes les lignes"""
        return self.routes
    
    def get_route_by_id(self, route_id):
        """
        Récupère une ligne par ID
        
        Args:
            route_id: ID de la ligne
            
        Returns:
            Series ou None
        """
        result = self.routes[self.routes['route_id'] == route_id]
        return result.iloc[0] if len(result) > 0 else None
    
    def get_trips_by_route(self, route_id):
        """
        Récupère tous les voyages d'une ligne
        
        Args:
            route_id: ID de la ligne
            
        Returns:
            DataFrame des voyages
        """
        return self.trips[self.trips['route_id'] == route_id]
    
    def get_trip_by_id(self, trip_id):
        """
        Récupère un voyage par ID
        
        Args:
            trip_id: ID du voyage
            
        Returns:
            Series ou None
        """
        result = self.trips[self.trips['trip_id'] == trip_id]
        return result.iloc[0] if len(result) > 0 else None


# Test du module
if __name__ == "__main__":
    print("=" * 60)
    print("***** TEST ROUTES TRIPS MANAGER")
    print("=" * 60)
    
    # Initialiser
    manager = RoutesTripsManager("data/gtfs")
    
    # Test 1: Lignes
    print("\n----- Quelques lignes:")
    print(manager.routes.head()[['route_id', 'route_short_name', 'route_long_name']])
    
    # Test 2: Voyages d'une ligne
    sample_route = manager.routes['route_id'].iloc[0]
    print(f"\n******Voyages de la ligne {sample_route}:")
    trips = manager.get_trips_by_route(sample_route)
    print(f"   Nombre de voyages: {len(trips)}")
    if len(trips) > 0:
        print(trips.head()[['trip_id', 'trip_headsign']])
    
    print("\n****** RoutesTripsManager fonctionne !")


