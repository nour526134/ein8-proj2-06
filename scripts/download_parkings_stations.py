"""
Récupère les parkings P+R et gares depuis OpenStreetMap
"""
import overpy
import json
import pandas as pd
from pathlib import Path

def get_parkings_bordeaux():
    """Récupère les parkings P+R de Bordeaux"""
    
    print("=" * 60)
    print(" RÉCUPÉRATION DES PARKINGS P+R")
    print("=" * 60)
    
    api = overpy.Overpass()
    
    query = """
    [out:json][timeout:25];
    (
      node["amenity"="parking"]["park_ride"="yes"](44.7,-0.7,44.95,-0.45);
      way["amenity"="parking"]["park_ride"="yes"](44.7,-0.7,44.95,-0.45);
      node["amenity"="parking"](around:800,44.826134,-0.555619);
      way["amenity"="parking"](around:800,44.826134,-0.555619);
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
        
        Path("data/osm").mkdir(parents=True, exist_ok=True)
        
        with open("data/osm/parkings.json", 'w', encoding='utf-8') as f:
            json.dump(parkings, f, ensure_ascii=False, indent=2)
        
        pd.DataFrame(parkings).to_csv("data/osm/parkings.csv", index=False)
        
        print(" Sauvegardé: data/osm/parkings.json & .csv")
        
        for p in parkings[:5]:
            print(f"   - {p['name']}")
        
        return parkings
        
    except Exception as e:
        print(f" Erreur: {e}")
        return []


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
    out center;
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
    parkings = get_parkings_bordeaux()
    stations = get_train_stations_bordeaux()
    
    print("\n" + "**" * 30)
    print("  DONNÉES OSM RÉCUPÉRÉES !")
    print("**" * 30)
