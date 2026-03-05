
"""
Service GTFS principal
Version SIMPLIFIÉE : ignore le calendrier
"""
# import pandas as pd
# from datetime import datetime
# from src.gtfs.stops_manager import StopsManager
# from src.gtfs.routes_trip_manager import RoutesTripsManager
# from src.gtfs.stop_times_manager import StopTimesManager

from unittest import result

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
    
    def __init__(self, gtfs_path="data/gtfs_bordeaux"):
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
            self.calendar_dates = pd.read_csv(f"{gtfs_path}/calendar_dates.csv")
            print(f" calendar_dates.csv chargé ({len(self.calendar_dates):,} dates)")
        except FileNotFoundError:
            self.calendar_dates = None
            print(" Pas de fichier calendar_dates.csv")
        
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
        UNIQUEMENT celles qui ont des trains disponibles
        """
        stops = self.stops_mgr.get_all_stops()
        
        # Filtrer selon le type
        if stop_areas_only and 'location_type' in stops.columns:
            stops = stops[stops['location_type'] == 1]
        
        # Sélectionner les colonnes importantes
        columns = ['stop_id', 'stop_name', 'stop_lat', 'stop_lon']
        if 'location_type' in stops.columns:
            columns.append('location_type')
        
        available_columns = [col for col in columns if col in stops.columns]
        
        result = stops[available_columns].copy()
        
        # Filtrer les stops sans coordonnées
        if 'stop_lat' in result.columns and 'stop_lon' in result.columns:
            result = result.dropna(subset=['stop_lat', 'stop_lon'])
        
        # ✅ CORRECTION : Ne garder QUE les stations avec horaires
        valid_stop_ids = set(self.stop_times_mgr.stop_times['stop_id'].unique())
        all_stops = self.stops_mgr.get_all_stops()
        
        # ✅ NE PLUS FILTRER PAR "Train" - Prendre TOUS les enfants dans stop_times
        valid_children = all_stops[all_stops['stop_id'].isin(valid_stop_ids)]
        
        valid_parents = set(valid_children['parent_station'].dropna().unique())
        result = result[result['stop_id'].isin(valid_parents)]
        
        # Vérifier qu'au moins 1 train existe
        verified_stations = []
        
        for stop_id in result['stop_id'].unique():
            children = self.stops_mgr.get_stoppoints_for_area(stop_id)
            
            if len(children) > 0:
                child_ids = children['stop_id'].tolist()
                has_trains = self.stop_times_mgr.stop_times['stop_id'].isin(child_ids).any()
                
                if has_trains:
                    verified_stations.append(stop_id)
        
        result = result[result['stop_id'].isin(verified_stations)]
        
        print(f"✅ Stations filtrées: {len(result)} stations avec trains disponibles")
        
        stops_df = result.reset_index(drop=True)
        
        # Convertir en dictionnaire
        stations = {}
        for _, row in stops_df.iterrows():
            stations[row['stop_id']] = {
                'id': row['stop_id'], 
                'lat': row['stop_lat'],
                'lon': row['stop_lon'],
                'name': row['stop_name']
            }
        
        return stations
    def get_all_stops_for_trip(self, trip_id, include_station_name=True):
        """
        Retourne TOUS les arrêts d'un voyage (trip) dans l'ordre
        
        Args:
            trip_id: ID du voyage
            include_station_name: Si True, ajoute le nom de la gare (StopArea)
            
        Returns:
            DataFrame avec colonnes:
                - stop_sequence: ordre de passage
                - stop_id: ID de l'arrêt (StopPoint)
                - stop_name: nom du StopPoint
                - station_name: nom de la gare (StopArea parent) ✨ NOUVEAU
                - arrival_time: heure d'arrivée
                - departure_time: heure de départ
                - stop_lat: latitude
                - stop_lon: longitude
        """
        # Récupérer les stop_times pour ce trip
        trip_stops = self.stop_times_mgr.stop_times[
            self.stop_times_mgr.stop_times['trip_id'] == trip_id
        ].copy()
        
        if len(trip_stops) == 0:
            return pd.DataFrame()
        
        # Trier par ordre de passage
        trip_stops = trip_stops.sort_values('stop_sequence')
        
        # Joindre avec stops pour avoir noms et coordonnées
        stops = self.stops_mgr.stops.copy()
        
        result = trip_stops.merge(
            stops[['stop_id', 'stop_name', 'stop_lat', 'stop_lon', 'parent_station', 'location_type']],
            on='stop_id',
            how='left'
        )
        
        #  Ajouter le nom de la gare (StopArea)
        if include_station_name and 'parent_station' in result.columns:
            # Créer un mapping parent_station -> nom de la StopArea
            stopareas = stops[stops['location_type'] == 1][['stop_id', 'stop_name']].copy()
            stopareas = stopareas.rename(columns={'stop_id': 'parent_station', 'stop_name': 'station_name'})
            
            # Joindre
            result = result.merge(stopareas, on='parent_station', how='left')
            
            # Si pas de parent_station, utiliser stop_name comme station_name
            result['station_name'] = result['station_name'].fillna(result['stop_name'])
        else:
            result['station_name'] = result['stop_name']
        
        # Sélectionner les colonnes utiles
        columns = [
            'stop_sequence',
            'stop_id',
            'stop_name',
            'station_name',  
            'arrival_time',
            'departure_time',
            'stop_lat',
            'stop_lon'
        ]
        
        available_columns = [col for col in columns if col in result.columns]
        
        return result[available_columns].reset_index(drop=True)

    def get_trip_origin_destination(self, trip_id):
        """
        Retourne l'origine et la destination d'un trip avec coordonnées
        """
        all_stops = self.get_all_stops_for_trip(trip_id)
        
        if len(all_stops) == 0:
            return None
        
        origin = all_stops.iloc[0]
        destination = all_stops.iloc[-1]
        
        return {
            'origin': {
                'stop_id': origin['stop_id'],
                'stop_name': origin['stop_name'],
                'station_name': origin.get('station_name', origin['stop_name']),  
                'lat': origin.get('stop_lat'),
                'lon': origin.get('stop_lon'),
                'departure_time': origin['departure_time']
            },
            'destination': {
                'stop_id': destination['stop_id'],
                'stop_name': destination['stop_name'],
                'station_name': destination.get('station_name', destination['stop_name']),  
                'lat': destination.get('stop_lat'),
                'lon': destination.get('stop_lon'),
                'arrival_time': destination['arrival_time']
            },
            'total_stops': len(all_stops),
            'intermediate_stops': len(all_stops) - 2,
            'all_stops': all_stops
        }

    def get_next_station_of_next_train(self, station_id, current_time=None):
        """
        Retourne la prochaine gare du prochain train
        
        Args:
            station_id: ID de la gare de départ
            current_time: Heure actuelle (format "HH:MM:SS" ou datetime)
            
        Returns:
            dict: {
                'current_station': {...},
                'next_station': {...},
                'train_info': {...},
                'all_remaining_stops': DataFrame
            }
            ou None si aucun train
        """
        # Convertir current_time
        if current_time is None:
            current_time = datetime.now().strftime("%H:%M:%S")
        elif isinstance(current_time, float):
            current_time =self.float_hour_to_hhmmss(current_time)
        
        # Trouver le prochain train
        next_trains = self.get_next_trains(station_id, current_time, limit=1)
        
        if len(next_trains) == 0:
            return None
        
        next_train = next_trains.iloc[0]
        trip_id = next_train['trip_id']
        
        # Récupérer tous les arrêts de ce train
        all_stops = self.get_all_stops_for_trip(trip_id)
        
        if len(all_stops) == 0:
            return None
        
        # Convertir station_id en StopPoints si nécessaire
        stop_ids_to_check = self._get_queryable_stop_ids(station_id)
        
        # Trouver l'arrêt actuel dans le voyage
        current_stop_idx = None
        
        for idx, (_, stop) in enumerate(all_stops.iterrows()):
            if stop['stop_id'] in stop_ids_to_check:
                current_stop_idx = idx
                break
        
        if current_stop_idx is None:
            # La gare n'est pas dans ce train (ne devrait pas arriver)
            return None
        
        # Vérifier s'il y a un arrêt suivant
        if current_stop_idx >= len(all_stops) - 1:
            # C'est le terminus
            return {
                'current_station': {
                    'stop_id': all_stops.iloc[current_stop_idx]['stop_id'],
                    'stop_name': all_stops.iloc[current_stop_idx]['stop_name'],
                    'station_name': all_stops.iloc[current_stop_idx].get('station_name'),
                    'departure_time': all_stops.iloc[current_stop_idx]['departure_time'],
                    'lat': all_stops.iloc[current_stop_idx].get('stop_lat'),
                    'lon': all_stops.iloc[current_stop_idx].get('stop_lon')
                },
                'next_station': None,
                'is_terminus': True,
                'train_info': {
                    'trip_id': trip_id,
                    'departure_time': next_train['departure_time'],
                    'direction': next_train.get('trip_headsign', 'N/A'),
                    'route': next_train.get('route_short_name', 'N/A')
                },
                'all_remaining_stops': pd.DataFrame()
            }

        # Récupérer l'arrêt suivant
        current_stop = all_stops.iloc[current_stop_idx]
        next_stop = all_stops.iloc[current_stop_idx + 1]
        remaining_stops = all_stops.iloc[current_stop_idx + 1:]
        
        return {
            'current_station': {
                'stop_id': current_stop['stop_id'],
                'stop_name': current_stop['stop_name'],
                'station_name': current_stop.get('station_name'),
                'departure_time': current_stop['departure_time'],
                'lat': current_stop.get('stop_lat'),
                'lon': current_stop.get('stop_lon')
            },
            'next_station': {
                'stop_id': next_stop['stop_id'],
                'stop_name': next_stop['stop_name'],
                'station_name': next_stop.get('station_name'),
                'arrival_time': next_stop['arrival_time'],
                'departure_time': next_stop['departure_time'],
                'lat': next_stop.get('stop_lat'),
                'lon': next_stop.get('stop_lon')
            },
            'is_terminus': False,
            'train_info': {
                'trip_id': trip_id,
                'departure_time': next_train['departure_time'],
                'direction': next_train.get('trip_headsign', 'N/A'),
                'route': next_train.get('route_short_name', 'N/A')
            },
            'all_remaining_stops': remaining_stops,
            'total_remaining_stops': len(remaining_stops)
    }

    def get_reachable_stations(self, station_id, current_time=None, min_trips=1):
        """
        Retourne toutes les gares accessibles depuis une gare (qui partagent au moins un trip)
        
        Args:
            station_id: Gare de départ
            current_time: Heure actuelle (optionnel, pour filtrer les trains futurs)
            min_trips: Nombre minimum de trips communs
            
        Returns:
            DataFrame: gares accessibles avec colonnes:
                - destination_station_id
                - destination_station_name
                - destination_lat
                - destination_lon
                - trip_count: nombre de trips qui y vont
                - sample_trip_id: exemple de trip
        """
        # Convertir en StopPoints
        origin_stop_ids = self._get_queryable_stop_ids(station_id)
        
        if not origin_stop_ids:
            return pd.DataFrame()
        
        # Trouver tous les trips passant par cette gare
        stop_times = self.stop_times_mgr.stop_times
        
        origin_trips = stop_times[stop_times['stop_id'].isin(origin_stop_ids)].copy()
        
        # Filtrer par heure si spécifié
        if current_time is not None:
            if isinstance(current_time, float):
                current_time = self.float_hour_to_hhmmss(current_time)
            origin_trips = origin_trips[origin_trips['departure_time'] >= current_time]
        
        trip_ids = origin_trips['trip_id'].unique()
        
        # Trouver tous les arrêts de ces trips
        all_stops_of_trips = stop_times[stop_times['trip_id'].isin(trip_ids)].copy()
        
        # Exclure la gare de départ
        destination_stops = all_stops_of_trips[~all_stops_of_trips['stop_id'].isin(origin_stop_ids)]
        
        # Grouper par stop_id pour compter les trips
        reachable = destination_stops.groupby('stop_id').agg({
            'trip_id': ['count', 'first']
        }).reset_index()
        
        reachable.columns = ['stop_id', 'trip_count', 'sample_trip_id']
        
        # Filtrer par nombre minimum de trips
        reachable = reachable[reachable['trip_count'] >= min_trips]
        
        # Joindre avec stops pour avoir les noms et coordonnées
        stops = self.stops_mgr.stops
        
        reachable = reachable.merge(
            stops[['stop_id', 'stop_name', 'stop_lat', 'stop_lon', 'parent_station', 'location_type']],
            on='stop_id',
            how='left'
        )
        
        # Ajouter station_name (StopArea)
        if 'parent_station' in reachable.columns and 'location_type' in stops.columns:
            stopareas = stops[stops['location_type'] == 1][['stop_id', 'stop_name']].copy()
            stopareas = stopareas.rename(columns={'stop_id': 'parent_station', 'stop_name': 'station_name'})
            
            reachable = reachable.merge(stopareas, on='parent_station', how='left')
            reachable['station_name'] = reachable['station_name'].fillna(reachable['stop_name'])
        else:
            reachable['station_name'] = reachable['stop_name']
        
        # Grouper par StopArea pour éviter les doublons
        if 'parent_station' in reachable.columns:
            reachable_grouped = reachable.groupby('parent_station').agg({
                'station_name': 'first',
                'stop_lat': 'first',
                'stop_lon': 'first',
                'trip_count': 'sum',
                'sample_trip_id': 'first'
            }).reset_index()
            
            reachable_grouped = reachable_grouped.rename(columns={'parent_station': 'destination_station_id'})
        else:
            reachable_grouped = reachable.rename(columns={
                'stop_id': 'destination_station_id',
                'station_name': 'destination_station_name'
            })
        
        # Nettoyer les colonnes
        result_columns = [
            'destination_station_id',
            'station_name',
            'stop_lat',
            'stop_lon',
            'trip_count',
            'sample_trip_id'
        ]
        
        available = [col for col in result_columns if col in reachable_grouped.columns]
        result = reachable_grouped[available].copy()
        
        if 'station_name' in result.columns:
            result = result.rename(columns={'station_name': 'destination_station_name'})
        
        result = result.rename(columns={
            'stop_lat': 'destination_lat',
            'stop_lon': 'destination_lon'
        })
        
        # Trier par nombre de trips (plus accessible en premier)
        result = result.sort_values('trip_count', ascending=False)
        
        return result.reset_index(drop=True)
    
    def float_hour_to_hhmmss(self,hour_float):
        """
        Convertit un float (ex: 8.25) en string "HH:MM:SS"
        """
        h = int(hour_float)
        m = int((hour_float - h) * 60)
        s = int((((hour_float - h) * 60) - m) * 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    def train_wait_time(self, station_id, current_time, destination_id=None, search_next_day=True, max_wait_hours=12):
        """
        Retourne le temps d'attente avant le prochain train (en minutes)
        
        Args:
            station_id: ID de la gare de départ (StopArea ou StopPoint)
            current_time: Heure actuelle ("HH:MM:SS" OU float en MINUTES OU datetime)
            destination_id: ID de la gare de destination (optionnel)
            search_next_day: Si True, cherche aussi le lendemain si aucun train aujourd'hui
            max_wait_hours: Temps d'attente maximum en heures (défaut: 12h)
            
        Returns:
            float: Temps d'attente en minutes (ou None si aucun train ou attente > max)
        """
        # ✅ CONVERSION : Gérer tous les formats de temps
        if isinstance(current_time, float):
            if current_time > 24:
                current_time_str = self.minutes_to_time_str(current_time)
            else:
                current_time_str = self.float_hour_to_hhmmss(current_time)
        elif isinstance(current_time, datetime):
            current_time_str = current_time.strftime("%H:%M:%S")
        else:
            current_time_str = current_time
        
        # Si pas de destination spécifiée
        if destination_id is None:
            trains = self.get_next_trains(station_id, current_time_str, limit=1)
            
            if len(trains) == 0:
                return None
            
            next_train_time = trains.iloc[0]['departure_time']
            wait_minutes = self._calculate_time_difference(current_time_str, next_train_time)
            
            return wait_minutes
        
        # ✅ AVEC DESTINATION
        else:
            # Convertir les IDs en StopPoints
            origin_stop_ids = self._get_queryable_stop_ids(station_id)
            dest_stop_ids = self._get_queryable_stop_ids(destination_id)
            
            if not origin_stop_ids or not dest_stop_ids:
                print(f"[DEBUG] ❌ Impossible de convertir les IDs en StopPoints")
                return None
            
            print(f"\n[DEBUG] origin_stop_ids: {origin_stop_ids}")
            print(f"[DEBUG] dest_stop_ids: {dest_stop_ids}")
            
            # ═══════════════════════════════════════════════════════════
            # ÉTAPE 1 : Chercher après l'heure actuelle (MÊME JOUR)
            # ═══════════════════════════════════════════════════════════
            
            result = self._search_trains_to_destination(
                origin_stop_ids,
                dest_stop_ids,
                current_time_str,
                station_id,
                destination_id,
                search_from_time=current_time_str
            )
            
            if result is not None:
                wait_minutes = self._calculate_time_difference(current_time_str, result['departure_time'])
                
                # Vérifier attente max
                if wait_minutes <= max_wait_hours * 60:
                    print(f"[DEBUG] ✅ Train trouvé AUJOURD'HUI: départ {result['departure_time']}, attente {wait_minutes:.0f} min")
                    return wait_minutes
                else:
                    print(f"[DEBUG] ⚠️ Train trop tard aujourd'hui ({wait_minutes:.0f} min > {max_wait_hours*60} min)")
            
            # ═══════════════════════════════════════════════════════════
            # ÉTAPE 2 : Chercher le LENDEMAIN (depuis minuit)
            # ════════════════════════════════���══════════════════════════
            
            if not search_next_day:
                print(f"[DEBUG] ❌ Aucun train aujourd'hui, search_next_day=False")
                return None
            
            print(f"[DEBUG] ⏰ Aucun train aujourd'hui, recherche LENDEMAIN...")
            
            result_tomorrow = self._search_trains_to_destination(
                origin_stop_ids,
                dest_stop_ids,
                "00:00:00",  # Depuis minuit
                station_id,
                destination_id,
                search_from_time="00:00:00"
            )
            
            if result_tomorrow is not None:
                # Calculer temps d'attente total
                # = temps jusqu'à minuit + temps depuis minuit
                
                wait_to_midnight = self._calculate_time_difference(current_time_str, "24:00:00")
                wait_from_midnight = self._calculate_time_difference("00:00:00", result_tomorrow['departure_time'])
                
                total_wait = wait_to_midnight + wait_from_midnight
                
                # Vérifier attente max
                if total_wait <= max_wait_hours * 60:
                    print(f"[DEBUG] ✅ Train trouvé LENDEMAIN: départ {result_tomorrow['departure_time']}")
                    print(f"[DEBUG]    Attente totale: {total_wait:.0f} min (~{total_wait/60:.1f}h)")
                    return total_wait
                else:
                    print(f"[DEBUG] ⚠️ Train lendemain trop tard ({total_wait:.0f} min > {max_wait_hours*60} min)")
            
            # ═══════════════════════════════════════════════════════════
            # ÉTAPE 3 : Vraiment aucun train
            # ═══════════════════════════════════════════════════════════
            
            print(f"[DEBUG] ❌❌❌ AUCUN TRAIN VALIDE trouvé")
            return None


    def _search_trains_to_destination(self, origin_stop_ids, dest_stop_ids, current_time_str, station_id, destination_id, search_from_time):
        """
        Cherche les trains qui vont de origin vers destination après une heure donnée
        
        Returns:
            dict avec 'departure_time' et 'trip_id', ou None si aucun train
        """
        stop_times = self.stop_times_mgr.stop_times
        
        # Trips passant par l'origine après search_from_time
        origin_trips = stop_times[
            (stop_times['stop_id'].isin(origin_stop_ids)) &
            (stop_times['departure_time'] >= search_from_time)
        ].copy()
        
        # Trier par heure de départ (pour avoir le premier)
        origin_trips = origin_trips.sort_values('departure_time')
        
        print(f"[DEBUG] Trains depuis {station_id} après {search_from_time}: {len(origin_trips)}")
        
        if len(origin_trips) == 0:
            return None
        
        # Chercher le premier train qui va vers la destination
        for _, origin_row in origin_trips.iterrows():
            trip_id = origin_row['trip_id']
            origin_seq = origin_row['stop_sequence']
            
            # Vérifier si ce trip passe par la destination APRÈS l'origine
            dest_rows = stop_times[
                (stop_times['trip_id'] == trip_id) &
                (stop_times['stop_id'].isin(dest_stop_ids))
            ]
            
            if len(dest_rows) == 0:
                continue
            
            dest_row = dest_rows.iloc[0]
            dest_seq = dest_row['stop_sequence']
            
            # Vérifier l'ordre (destination APRÈS origine)
            if dest_seq > origin_seq:
                print(f"[DEBUG]   ✅ Train valide: {trip_id[:50]}...")
                print(f"[DEBUG]      Origine seq={origin_seq}, Dest seq={dest_seq}")
                print(f"[DEBUG]      Départ: {origin_row['departure_time']}")
                
                return {
                    'departure_time': origin_row['departure_time'],
                    'trip_id': trip_id
                }
            else:
                # Train dans le mauvais sens, continuer
                continue
        
        return None
                
                
                    
            
    def minutes_to_time_str(self, minutes):
            """
            Convertit un temps en minutes en format "HH:MM:SS"
            
            Exemple:
                90 -> "01:30:00"
                488 -> "08:08:00"
            """
            total_seconds = int(round(minutes * 60))
            
            h = total_seconds // 3600
            m = (total_seconds % 3600) // 60
            s = total_seconds % 60

            return f"{h:02d}:{m:02d}:{s:02d}"
    def train_trip_time(self, station_id, destination_id):
        """
        Retourne la durée du trajet en train depuis la gare jusqu'à la destination (en minutes)
        
        Args:
            station_id: ID de la gare de départ (StopArea ou StopPoint)
            destination_id: ID de la gare d'arrivée (StopArea ou StopPoint)
            
        Returns:
            float: Durée du trajet en minutes (moyenne si plusieurs trips)
                   None si aucune connexion trouvée
        """
        # Convertir en StopPoints si nécessaire
        origin_stop_ids = self._get_queryable_stop_ids(station_id)
        dest_stop_ids = self._get_queryable_stop_ids(destination_id)
        
        if not origin_stop_ids or not dest_stop_ids:
            return None
        
        # Chercher des trips qui passent par origine ET destination
        trip_durations = []
        
        for origin_sid in origin_stop_ids:
            for dest_sid in dest_stop_ids:
                duration = self._find_trip_duration(origin_sid, dest_sid)
                if duration is not None:
                    trip_durations.append(duration)
        
        if not trip_durations:
            return None
        
        # Retourner la durée moyenne
        return sum(trip_durations) / len(trip_durations)
    
    def _find_trip_duration(self, origin_stop_id, dest_stop_id):
        """
        Trouve la durée d'un trip entre deux stops
        
        Returns:
            float: Durée en minutes, ou None si pas de connexion
        """
        # Charger stop_times
        stop_times = self.stop_times_mgr.stop_times
        
        origin_times = stop_times[stop_times['stop_id'] == origin_stop_id].reset_index(drop=True)
        dest_times = stop_times[stop_times['stop_id'] == dest_stop_id].reset_index(drop=True)
        
        # Trips en commun
        common_trips = set(origin_times['trip_id']) & set(dest_times['trip_id'])
        
        if not common_trips:
            return None
        
        durations = []
        
        for trip_id in common_trips:
            origin_row = origin_times[origin_times['trip_id'] == trip_id].iloc[0]
            dest_row = dest_times[dest_times['trip_id'] == trip_id].iloc[0]
            
            # Vérifier que destination est après origine (stop_sequence)
            if dest_row['stop_sequence'] > origin_row['stop_sequence']:
                departure = origin_row['departure_time']
                arrival = dest_row['arrival_time']
                
                duration_min = self._calculate_time_difference(departure, arrival)
                durations.append(duration_min)
        
        if not durations:
            return None
        
        # Retourner la durée minimale (trajet le plus rapide)
        return min(durations)


    
    def _calculate_time_difference(self, time1, time2):
        """
        Calcule la différence entre deux heures GTFS (en minutes)
        
        Args:
            time1: Heure de début ("HH:MM:SS")
            time2: Heure de fin ("HH:MM:SS")
            
        Returns:
            float: Différence en minutes (time2 - time1)
        """
        def parse_gtfs_time(time_str):
            """Parse une heure GTFS (peut dépasser 24h)"""
            parts = time_str.split(':')
            hours = int(parts[0])
            minutes = int(parts[1])
            seconds = int(parts[2])
            return hours * 60 + minutes + seconds / 60
        
        minutes1 = parse_gtfs_time(time1)
        minutes2 = parse_gtfs_time(time2)
        
        diff = minutes2 - minutes1
        
        # Gérer le cas où on passe minuit
        if diff < 0:
            diff += 24 * 60
        
        return diff
    
    def _get_queryable_stop_ids(self, stop_id):
        """
        Convertit un stop_id en liste de stop_ids utilisables
        """
        stop = self.stops_mgr.get_stop_by_id(stop_id)
        
        if stop is None:
            return []
        
        # Si location_type existe
        if self.stops_mgr.has_location_type:
            location_type = stop.get('location_type')
            
            # Si c'est une StopArea (location_type = 1)
            if location_type == 1:
                # Récupérer TOUS les enfants
                children = self.stops_mgr.get_stoppoints_for_area(stop_id)
                
                if len(children) > 0:
                    child_ids = children['stop_id'].tolist()
                    
                    # ✅ NE PAS FILTRER - Retourner TOUS les enfants
                    # même ceux qui ne sont pas dans stop_times
                    # (car ils peuvent être dans certains trips)
                    return child_ids
            
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

        stop_ids_to_query = self._get_queryable_stop_ids(stop_id)
        print(f"[DEBUG] stop_ids_to_query={stop_ids_to_query}")
        print(f"[DEBUG] Exemples stop_id dans stop_times: {self.stop_times_mgr.stop_times['stop_id'].head(10).tolist()}")

        if current_time is None:
            current_time = datetime.now().strftime("%H:%M:%S")
        
        # Dans get_next_trains ou _get_queryable_stop_ids, ajoute :
        children = self.stops_mgr.get_stoppoints_for_area("StopArea:OCE87582718")
        print(f"[DEBUG] Enfants de StopArea:OCE87582718 : {len(children)}")
        print(children[['stop_id', 'stop_name', 'parent_station']].head())
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
    
    service = GTFSService("data/gtfs_bordeaux")
    
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
