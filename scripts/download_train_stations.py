import overpy
import json
import pandas as pd
from pathlib import Path


def get_train_stations_bordeaux():
    """Récupère les gares"""
    
    print("\n" + "=" * 60)
    print(" RÉCUPÉRATION DES GARES")
    print("=" * 60)
    
    api = overpy.Overpass()
    
    query = """
    [out:json][timeout:25];
    (
      node["railway"="station"](44.7,-0.7,44.95,-0.45);
      node["railway"="halt"](44.7,-0.7,44.95,-0.45);
      way["railway"="station"](44.7,-0.7,44.95,-0.45);
    );
    out center 200;
    """
    
    print("\n Requête Overpass API...\n")
    
    try:
        result = api.query(query)
        stations = []
        
        for node in result.nodes:
            stations.append({
                'id': f"node_{node.id}",
                'lat': float(node.lat),
                'lon': float(node.lon),
                'name': node.tags.get('name', 'Gare sans nom'),
                'railway': node.tags.get('railway', 'unknown')
            })
        
        for way in result.ways:
            if hasattr(way, 'center_lat'):
                lat, lon = way.center_lat, way.center_lon
            else:
                lats = [float(n.lat) for n in way.nodes]
                lons = [float(n.lon) for n in way.nodes]
                lat = sum(lats) / len(lats)
                lon = sum(lons) / len(lons)
            
            stations.append({
                'id': f"way_{way.id}",
                'lat': float(lat),
                'lon': float(lon),
                'name': way.tags.get('name', 'Gare sans nom'),
                'railway': way.tags.get('railway', 'unknown')
            })
        
        print(f" {len(stations)} gares trouvées\n")
        
        with open("data/osm/stations.json", 'w', encoding='utf-8') as f:
            json.dump(stations, f, ensure_ascii=False, indent=2)
        
        pd.DataFrame(stations).to_csv("data/osm/stations.csv", index=False)
        
        print(" Sauvegardé: data/osm/stations.json & .csv")
        
        for s in stations:
            print(f"   - {s['name']}")
        
        return stations
        
    except Exception as e:
        print(f" Erreur: {e}")
        return []

if __name__ == "__main__":
    stations = get_train_stations_bordeaux()
    
    print("\n" + "**" * 30)
    print("  DONNÉES OSM RÉCUPÉRÉES !")
    print("**" * 30)
