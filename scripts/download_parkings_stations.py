import overpy
import json
import pandas as pd
from pathlib import Path
from typing import List, Dict, Any

def get_parkings_from_osm(data_path="../data/osm") -> List[Dict[str, Any]]:
    """
    Récupère les parkings de Bordeaux Métropole depuis OSM
    Retourne une liste de dictionnaires
    """
    
    print("=" * 60)
    print(" RÉCUPÉRATION DES PARKINGS P+R")
    print("=" * 60)
    
    api = overpy.Overpass()
    
    # Requête Overpass
    query = """
[out:json];
area["name"="Bordeaux Métropole"]->.bm;
(
  node["amenity"="parking"](area.bm);
  way["amenity"="parking"](area.bm);
  relation["amenity"="parking"](area.bm);
);
out center;
    """
    
    print("\n Requête Overpass API...\n")
    
    try:
        result = api.query(query)
        parkings = []
        
        # Traiter les nodes
        for node in result.nodes:
            capacity = node.tags.get("capacity")
            if capacity:
                try:
                    capacity = int(capacity)
                except ValueError:
                    capacity = None
            
            parking = {
                'id': str(node.id),
                'lat': float(node.lat),
                'lon': float(node.lon),
                'name': node.tags.get("name", f"Parking_{node.id}"),
                'capacity': capacity,
                'type': 'node',
                'source': 'osm'
            }
            parkings.append(parking)
        
        # Traiter les ways
        for way in result.ways:
            capacity = way.tags.get("capacity")
            if capacity:
                try:
                    capacity = int(capacity)
                except ValueError:
                    capacity = None
            
            # Obtenir les coordonnées du centre
            if hasattr(way, 'center_lat') and hasattr(way, 'center_lon'):
                lat, lon = float(way.center_lat), float(way.center_lon)
            else:
                # Calculer le centroïde à partir des nodes
                if way.nodes:
                    lats = [float(n.lat) for n in way.nodes if hasattr(n, 'lat')]
                    lons = [float(n.lon) for n in way.nodes if hasattr(n, 'lon')]
                    if lats and lons:
                        lat = sum(lats) / len(lats)
                        lon = sum(lons) / len(lons)
                    else:
                        continue
                else:
                    continue
            
            parking = {
                'id': str(way.id),
                'lat': lat,
                'lon': lon,
                'name': way.tags.get("name", f"Parking_{way.id}"),
                'capacity': capacity,
                'type': 'way',
                'source': 'osm'
            }
            parkings.append(parking)
        
        # Créer le répertoire si nécessaire
        data_dir = Path(data_path)
        data_dir.mkdir(parents=True, exist_ok=True)
        
        # Sauvegarder en JSON
        json_path = data_dir / "parkings.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(parkings, f, ensure_ascii=False, indent=2)
        print(f"✅ Données sauvegardées dans {json_path}")
        
        # Sauvegarder en CSV
        csv_path = data_dir / "parkings.csv"
        df = pd.DataFrame(parkings)
        df.to_csv(csv_path, index=False)
        print(f"✅ Données sauvegardées dans {csv_path}")
        
        # Afficher les premiers parkings
        print(f"\n✅ {len(parkings)} parkings trouvés")
        print("\n📊 Exemples de parkings:")
        for p in parkings[:5]:
            capacity_str = f", capacité: {p['capacity']}" if p['capacity'] else ""
            print(f"   - {p['name']} ({p['lat']:.6f}, {p['lon']:.6f}){capacity_str}")
        
        return parkings
        
    except Exception as e:
        print(f"❌ Erreur: {e}")
        import traceback
        traceback.print_exc()
        return []


def get_parkings(data_path="../data/osm/parkings.csv"):
    df = pd.read_csv(data_path)
    parkings = df.to_dict('records')
    return parkings



def main_download_parkings():
    parkings = get_parkings_from_osm()
    # Afficher les 3 premiers parkings
    print("\n🏢 PREMIERS PARKINGS:")
    for p in parkings[:3]:
        print(f"   - {p}")
main_download_parkings()