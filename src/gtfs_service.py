
"""
Service GTFS principal
Version SIMPLIFIÉE : ignore le calendrier
"""
# import pandas as pd
# from datetime import datetime
# from src.gtfs.stops_manager import StopsManager
# from src.gtfs.routes_trip_manager import RoutesTripsManager
# from src.gtfs.stop_times_manager import StopTimesManager

import pandas as pd
from datetime import datetime

# # Imports compatibles pour exécution directe et import module
try:
    from .gtfs.stops_manager import StopsManager
    from .gtfs.routes_trip_manager import RoutesTripsManager
    from .gtfs.stop_times_manager import StopTimesManager
except ImportError:
    from gtfs.stops_manager import StopsManager
    from gtfs.routes_trip_manager import RoutesTripsManager
    from gtfs.stop_times_manager import StopTimesManager

class GTFSService:
    """Service principal pour consulter les horaires GTFS"""
    
    def __init__(self, gtfs_path="data/gtfs"):
        """
        Args:
            gtfs_path: Chemin vers le dossier GTFS
        """
        print("=" * 60)
        print(" Initialisation du service GTFS")
        print("=" * 60)
        
        self.stops_mgr = StopsManager(gtfs_path)
        self.routes_trips_mgr = RoutesTripsManager(gtfs_path)
        self.stop_times_mgr = StopTimesManager(gtfs_path)
        
        # Charger calendar_dates si disponible
        try:
            self.calendar_dates = pd.read_csv(f"{gtfs_path}/calendar_dates.txt")
            print(f" calendar_dates.txt chargé ({len(self.calendar_dates):,} dates)")
        except FileNotFoundError:
            self.calendar_dates = None
            print(" Pas de fichier calendar_dates.txt")
        
        print("\n" + "*" * 30)
        print("  Service GTFS prêt à utiliser !")
        print("*" * 30 + "\n")
    
    def find_station(self, name):
        """Recherche une gare par nom"""
        return self.stops_mgr.search_stop_by_name(name)
    
    def get_station_by_id(self, stop_id):
        """Récupère une gare par ID"""
        return self.stops_mgr.get_stop_by_id(stop_id)
    
    def get_major_stations(self):
        """Retourne les gares principales"""
        return self.stops_mgr.get_major_stations()
    
    def load_stops(self, stop_areas_only=True):
        """
        Retourne toutes les stations avec leurs coordonnées
        
        Args:
            stop_areas_only: Si True, ne retourne que les StopAreas (gares principales)
                           Si False, retourne tous les stops (y compris StopPoints)
        
        Returns:
            DataFrame avec colonnes: stop_id, stop_name, lat, lon, location_type
        """
        stops = self.stops_mgr.get_all_stops()
        
        # Filtrer selon le type
        if stop_areas_only and 'location_type' in stops.columns:
            stops = stops[stops['location_type'] == 1]
        
        # Sélectionner les colonnes importantes
        columns = ['stop_id', 'stop_name', 'lat', 'lon']
        if 'location_type' in stops.columns:
            columns.append('location_type')
        
        available_columns = [col for col in columns if col in stops.columns]
        
        result = stops[available_columns].copy()
        
        # Filtrer les stops sans coordonnées
        if 'lat' in result.columns and 'lon' in result.columns:
            result = result.dropna(subset=['lat', 'lon'])
        
        return result.reset_index(drop=True)
    
    def _get_queryable_stop_ids(self, stop_id):
        """
        Convertit un stop_id en liste de stop_ids utilisables
        
        Args:
            stop_id: ID de la gare
            
        Returns:
            list: Liste de stop_ids utilisables
        """
        stop = self.stops_mgr.get_stop_by_id(stop_id)
        
        if stop is None:
            return []
        
        # Si location_type existe
        if self.stops_mgr.has_location_type:
            location_type = stop.get('location_type')
            
            # Si c'est une StopArea (location_type = 1)
            if location_type == 1:
                # Trouver les StopPoints enfants
                children = self.stops_mgr.get_stoppoints_for_area(stop_id)
                
                if len(children) > 0:
                    return children['stop_id'].tolist()
            
            # Si c'est un StopPoint (location_type = 0)
            elif location_type == 0:
                return [stop_id]
        
        # Fallback
        return [stop_id]
    
    def get_next_trains(self, stop_id, current_time=None, limit=10, ignore_calendar=True):
        """
        Récupère les prochains trains
        
        Args:
            stop_id: ID de la gare (StopArea ou StopPoint)
            current_time: Heure ("HH:MM:SS")
            limit: Nombre de trains
            ignore_calendar: Si True, ignore les contraintes de calendrier
            
        Returns:
            DataFrame des prochains trains
        """
        if current_time is None:
            current_time = datetime.now().strftime("%H:%M:%S")
        
        # Convertir StopArea en StopPoint(s) si nécessaire
        stop_ids_to_query = self._get_queryable_stop_ids(stop_id)
        
        if not stop_ids_to_query:
            print(f" Aucun stop_id utilisable pour {stop_id}")
            return pd.DataFrame()
        
        # Requête pour chaque stop_id
        all_departures = []
        
        for sid in stop_ids_to_query:
            departures = self.stop_times_mgr.get_departures_after(
                sid,
                current_time,
                limit=limit * 10  # Prendre plus pour compenser le filtrage
            )
            all_departures.append(departures)
        
        if not all_departures:
            return pd.DataFrame()
        
        # Combiner tous les résultats
        result = pd.concat(all_departures, ignore_index=True)
        
        if len(result) == 0:
            return pd.DataFrame()
        
        # Jointures avec trips et routes
        result = result.merge(
            self.routes_trips_mgr.trips[['trip_id', 'route_id', 'trip_headsign']],
            on='trip_id',
            how='left'
        )
        
        result = result.merge(
            self.routes_trips_mgr.routes[['route_id', 'route_short_name', 'route_long_name']],
            on='route_id',
            how='left'
        )
        
        #  CORRECTION: Ne PAS filtrer par calendrier pour l'instant
        # (Les données sont des horaires théoriques sans lien avec des dates réelles)
        
        # Trier et limiter
        result = result.sort_values('departure_time')
        result = result.drop_duplicates(subset=['trip_id'])
        result = result.head(limit)
        
        # Colonnes finales
        columns = [
            'departure_time',
            'route_short_name',
            'route_long_name',
            'trip_headsign',
            'trip_id'
        ]
        
        available_columns = [col for col in columns if col in result.columns]
        
        return result[available_columns].reset_index(drop=True)
    
    


# Test
if __name__ == "__main__":
    print("\n" + "*" * 30)
    print("  TEST SERVICE GTFS (Sans filtrage calendrier)")
    print("*" * 30 + "\n")
    
    service = GTFSService("data/gtfs")
    
    # Rechercher Bordeaux
    print(" Recherche 'Bordeaux Saint-Jean':")
    bordeaux = service.find_station("Bordeaux Saint-Jean")

    all_stations = service.load_stops(stop_areas_only=True)
    print(f" {len(all_stations)} stations trouvées")
    print(all_stations.head())
    
    if len(bordeaux) > 0:
        # Prendre la première StopArea
        stoparea = bordeaux[bordeaux['location_type'] == 1].iloc[0] if 'location_type' in bordeaux.columns else bordeaux.iloc[0]
        
        print(f"\n Gare: {stoparea['stop_name']}")
        print(f"   ID: {stoparea['stop_id']}")
        
        # Tester plusieurs heures
        for time in ["06:00:00", "10:00:00", "14:00:00"]:
            print(f"\n{'='*60}")
            print(f" Trains après {time}")
            print(f"{'='*60}")
            
            trains = service.get_next_trains(stoparea['stop_id'], time, limit=5)
            
            if len(trains) > 0:
                print(trains.to_string(index=False))
            else:
                print("    Aucun train trouvé")
    else:
        print(" Aucune gare Bordeaux trouvée")
