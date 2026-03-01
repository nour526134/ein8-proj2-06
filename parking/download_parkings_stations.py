"""
Récupère les parkings P+R et gares depuis OpenStreetMap
"""
import overpy
import json
import pandas as pd
from pathlib import Path

class parking_downloader:
    def __init__(data_path):
        self.data_path="../data/osm"
    
    def get_parkings():
        """Récupère les parkings P+R de Bordeaux"""
        
        print("=" * 60)
        print(" RÉCUPÉRATION DES PARKINGS P+R")
        print("=" * 60)
        
        api = overpy.Overpass()
        
        query="""
        [out:json][timeout:120];

        rel["name"="Nouvelle-Aquitaine"]["boundary"="administrative"];
        map_to_area -> .na;    (
        node["amenity"="parking"](area.na);
        way["amenity"="parking"](area.na);
        relation["amenity"="parking"](area.na);
        );
        out center;
    """
        
        print("\n Requête Overpass API...\n")
        
        try:
            result = api.query(query)
            parkings = []
            
            for node in result.nodes:
                parkings.append({
                    'id': f"node_{node.id}",
                    'lat': float(node.lat),
                    'lon': float(node.lon),
                    'name': node.tags.get('name', 'Parking sans nom'),
                    'capacity': node.tags.get('capacity', 'N/A'),
                    'park_ride': node.tags.get('park_ride', 'unknown')
                })
            
            for way in result.ways:
                if hasattr(way, 'center_lat'):
                    lat, lon = way.center_lat, way.center_lon
                else:
                    lats = [float(n.lat) for n in way.nodes]
                    lons = [float(n.lon) for n in way.nodes]
                    lat = sum(lats) / len(lats)
                    lon = sum(lons) / len(lons)
                
                parkings.append({
                    'id': f"way_{way.id}",
                    'lat': float(lat),
                    'lon': float(lon),
                    'name': way.tags.get('name', 'Parking sans nom'),
                    'capacity': way.tags.get('capacity', 'N/A'),
                    'park_ride': way.tags.get('park_ride', 'unknown')
                })
            
            print(f" {len(parkings)} parkings trouvés\n")
            
            Path(data_path).mkdir(parents=True, exist_ok=True)
            
            with open(data_path+"/parkings.json", 'w', encoding='utf-8') as f:
                json.dump(parkings, f, ensure_ascii=False, indent=2)
            
            pd.DataFrame(parkings).to_csv(data_path+"/parkings.csv", index=False)
            
            
            for p in parkings[:5]:
                print(f"   - {p['name']}")
            
            return parkings
            
        except Exception as e:
            print(f" Erreur: {e}")
            return []