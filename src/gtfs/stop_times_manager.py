"""
Gestionnaire des horaires (stop_times.csv)
ATTENTION: Fichier volumineux, chargement optimisé
"""
import pandas as pd
from datetime import datetime, timedelta

class StopTimesManager:
    """Gère les horaires des trains"""
    
    def __init__(self, gtfs_path):
        """
        Args:
            gtfs_path: Chemin vers le dossier GTFS
        """
        print("???? Chargement des horaires (peut prendre 30-60 secondes)...")
        
        # Charger uniquement les colonnes nécessaires pour optimiser
        columns = [
            'trip_id',
            'arrival_time',
            'departure_time',
            'stop_id',
            'stop_sequence'
        ]
        
        # Charger avec optimisation mémoire
        self.stop_times = pd.read_csv(
            f"{gtfs_path}/stop_times.csv",
            usecols=columns,
            dtype={
                'trip_id': 'str',
                'stop_id': 'str',
                'stop_sequence': 'int32'
            }
        )
        
        print(f" {len(self.stop_times):,} horaires chargés")
    
    def get_stop_times_by_trip(self, trip_id):
        """
        Récupère tous les horaires d'un voyage
        
        Args:
            trip_id: ID du voyage
            
        Returns:
            DataFrame trié par séquence d'arrêt
        """
        return self.stop_times[
            self.stop_times['trip_id'] == trip_id
        ].sort_values('stop_sequence')
    
    def get_stop_times_by_stop(self, stop_id):
        """
        Récupère tous les horaires d'une gare
        
        Args:
            stop_id: ID de la gare
            
        Returns:
            DataFrame des horaires
        """
        return self.stop_times[self.stop_times['stop_id'] == stop_id]
    
    def get_departures_after(self, stop_id, time_str, limit=None):
        """
        Récupère les départs après une heure donnée
        
        Args:
            stop_id: ID de la gare
            time_str: Heure au format "HH:MM:SS"
            limit: Nombre max de résultats
            
        Returns:
            DataFrame des départs
        """
        # Filtrer par gare
        departures = self.stop_times[self.stop_times['stop_id'] == stop_id].copy()
        
        # Filtrer par heure
        print(time_str)
        departures = departures[departures['departure_time'] >= time_str]
        
        # Trier par heure
        departures = departures.sort_values('departure_time')
        
        # Limiter
        if limit:
            departures = departures.head(limit)
        
        return departures
    
    @staticmethod
    def parse_gtfs_time(time_str):
        """
        Convertit une heure GTFS en datetime
        
        Note: GTFS peut avoir des heures > 24 (ex: 25:30:00 = 01:30 le lendemain)
        
        Args:
            time_str: Heure GTFS "HH:MM:SS"
            
        Returns:
            datetime ou None
        """
        if pd.isna(time_str):
            return None
        
        try:
            parts = time_str.split(':')
            hours = int(parts[0])
            minutes = int(parts[1])
            seconds = int(parts[2])
            
            # Gérer les heures > 24
            days = hours // 24
            hours = hours % 24
            
            # Créer un datetime
            base_time = datetime.now().replace(
                hour=hours,
                minute=minutes,
                second=seconds,
                microsecond=0
            )
            
            return base_time + timedelta(days=days)
        except:
            return None


# Test du module
if __name__ == "__main__":
    print("=" * 60)
    print(" TEST STOP TIMES MANAGER")
    print("=" * 60)
    
    # Initialiser
    manager = StopTimesManager("data/gtfs_bordeaux")
    
    # Test 1: Horaires d'un voyage
    print("\n Horaires d'un voyage:")
    sample_trip = manager.stop_times['trip_id'].iloc[0]
    trip_schedule = manager.get_stop_times_by_trip(sample_trip)
    print(f"   Voyage: {sample_trip}")
    print(f"   Nombre d'arrêts: {len(trip_schedule)}")
    print(trip_schedule[['stop_id', 'arrival_time', 'departure_time']].head())
    
    # Test 2: Départs après 14:00
    print("\n Départs après 14:00 (première gare trouvée):")
    sample_stop = manager.stop_times['stop_id'].iloc[0]
    departures = manager.get_departures_after(sample_stop, "14:00:00", limit=5)
    print(f"   Gare: {sample_stop}")
    print(f"   Départs trouvés: {len(departures)}")
    if len(departures) > 0:
        print(departures[['trip_id', 'departure_time']].head())
    
    # Test 3: Parser une heure
    print("\n Test parsing d'heure:")
    test_times = ["14:30:00", "25:15:00", "08:00:00"]
    for time_str in test_times:
        parsed = manager.parse_gtfs_time(time_str)
        print(f"   {time_str} → {parsed}")
    
    print("\n StopTimesManager fonctionne !")


