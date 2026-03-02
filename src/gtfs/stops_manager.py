

"""
Gestionnaire des gares (stops.csv)
Version  pour gérer StopArea vs StopPoint
"""
import pandas as pd

class StopsManager:
    """Gère les gares et arrêts GTFS"""
    
    def __init__(self, gtfs_path):
        """
        Args:
            gtfs_path: Chemin vers le dossier GTFS
        """
        print(" Chargement des gares...")
        self.stops = pd.read_csv(f"{gtfs_path}/stops.csv")
        self._clean_data()
        
        #   Identifier le type de structure
        self.has_location_type = 'location_type' in self.stops.columns
        self.has_parent_station = 'parent_station' in self.stops.columns
        
        print(f" {len(self.stops):,} gares chargées")
        
        if self.has_location_type:
            stoppoints = len(self.stops[self.stops['location_type'] == 0])
            stopareas = len(self.stops[self.stops['location_type'] == 1])
            print(f"   - {stoppoints:,} StopPoints (points d'arrêt)")
            print(f"   - {stopareas:,} StopAreas (zones)")
    
    def _clean_data(self):
        """Nettoie les données"""
        self.stops = self.stops.drop_duplicates(subset=['stop_id'])
        self.stops['stop_name'] = self.stops['stop_name'].fillna('Unknown')
    
    def get_all_stops(self):
        """Retourne toutes les gares"""
        return self.stops
    
    def get_stoppoints_only(self):
        """
        Retourne uniquement les StopPoints (utilisables dans stop_times.csv)
        
        Returns:
            DataFrame des StopPoints
        """
        if self.has_location_type:
            # location_type = 0 → StopPoint
            return self.stops[self.stops['location_type'] == 0]
        else:
            # Fallback: retourner tout
            return self.stops
    
    def search_stop_by_name(self, name, stoppoints_only=False):
        """
        Recherche une gare par nom
        
        Args:
            name: Nom de la gare
            stoppoints_only: Si True, retourne uniquement les StopPoints
            
        Returns:
            DataFrame des gares correspondantes
        """
        mask = self.stops['stop_name'].str.contains(name, case=False, na=False)
        result = self.stops[mask]
        
        if stoppoints_only and self.has_location_type:
            result = result[result['location_type'] == 0]
        
        return result
    
    def get_stoppoints_for_area(self, area_id):
        """
        Récupère les StopPoints d'une StopArea
        
        Args:
            area_id: ID de la StopArea
            
        Returns:
            DataFrame des StopPoints enfants
        """
        if not self.has_parent_station:
            return pd.DataFrame()
        
        return self.stops[self.stops['parent_station'] == area_id]
    
    def find_usable_stop_id(self, stop_name):
        """
        Trouve un stop_id utilisable dans stop_times.csv
        
        Args:
            stop_name: Nom de la gare
            
        Returns:
            str: stop_id utilisable ou None
        """
        # Chercher la gare
        found = self.search_stop_by_name(stop_name)
        
        if len(found) == 0:
            return None
        
        # Prendre le premier résultat
        first = found.iloc[0]
        stop_id = first['stop_id']
        
        # Si c'est une StopArea, chercher un StopPoint enfant
        if self.has_location_type and first.get('location_type') == 1:
            children = self.get_stoppoints_for_area(stop_id)
            
            if len(children) > 0:
                return children.iloc[0]['stop_id']
        
        # Sinon, retourner l'ID tel quel
        return stop_id
    
    def get_stop_by_id(self, stop_id):
        """Récupère une gare par ID"""
        result = self.stops[self.stops['stop_id'] == stop_id]
        return result.iloc[0] if len(result) > 0 else None
    
    def get_major_stations(self):
        """Identifie les gares principales"""
        # Utiliser uniquement les StopAreas si disponible
        if self.has_location_type:
            major = self.stops[self.stops['location_type'] == 1].copy()
        else:
            major = self.stops.copy()
        
        # Filtrer par longueur de nom
        major['name_length'] = major['stop_name'].str.len()
        major = major[major['name_length'] >= 15]
        
        return major.sort_values('stop_name')


# Test du module
if __name__ == "__main__":
    print("=" * 60)
    print(" ******TEST STOPS MANAGER****")
    print("=" * 60)
    
    # Initialiser
    manager = StopsManager("data/gtfs")
    
    print(f"\n +++++Attributs disponibles:")
    print(f"   - has_location_type: {manager.has_location_type}")
    print(f"   - has_parent_station: {manager.has_parent_station}")
    
    # Test 1: Rechercher Bordeaux
    print("\n****** Recherche 'Bordeaux':")
    bordeaux = manager.search_stop_by_name("Bordeaux")
    print(f"   Total: {len(bordeaux)} gares")
    
    # Test 2: StopPoints uniquement
    print("\n***** StopPoints Bordeaux uniquement:")
    bordeaux_points = manager.search_stop_by_name("Bordeaux", stoppoints_only=True)
    print(f"   Total: {len(bordeaux_points)} StopPoints")
    if len(bordeaux_points) > 0:
        print(bordeaux_points[['stop_id', 'stop_name']].head(5).to_string(index=False))
    
    # Test 3: StopArea → StopPoints
    print("\n***** StopArea → StopPoints:")
    stoparea = bordeaux[bordeaux['location_type'] == 1].iloc[0] if 'location_type' in bordeaux.columns else bordeaux.iloc[0]
    print(f"   StopArea: {stoparea['stop_id']}")
    
    children = manager.get_stoppoints_for_area(stoparea['stop_id'])
    print(f"   Enfants: {len(children)} StopPoints")
    if len(children) > 0:
        print(children[['stop_id', 'stop_name']].head().to_string(index=False))
    
    print("\n********* StopsManager opérationnel !")
