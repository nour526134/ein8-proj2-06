"""
Récupère les parkings P+R et gares depuis OpenStreetMap
"""
import overpy
import json
import pandas as pd
from pathlib import Path

class Parking:
    def __init__(self,id,long,lat,name,capacity):
        self.id=id
        self.long=long
        self.lat=lat
        self.capacity=capacity
    def get_lat():
        return self.lat
    def get_long():
        return self.long
    def get_name():
        return self.name
    def get_capacity():
        return self.capacity
    def render_parking(self):
        print(f"Parking ID: {self.id}")
        print(f"Nom: {self.name}")
        print(f"Latitude: {self.lat}")
        print(f"Longitude: {self.long}")
        print(f"Capacité: {self.capacity}")


class parking_factory:
    def __init__(self,data_path):
        self.data_path=data_path
    
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
                parkings.append(Parking(node.id,node.lat,node.long,name,capacity))
            
            for way in result.ways:
                if hasattr(way, 'center_lat'):
                    lat, lon = way.center_lat, way.center_lon
                else:
                    lats = [float(n.lat) for n in way.nodes]
                    lons = [float(n.lon) for n in way.nodes]
                    lat = sum(lats) / len(lats)
                    lon = sum(lons) / len(lons)
                
                parkings.append(Parking(id,lat,lon,name,capacity))
            
            Path(self.data_path).mkdir(parents=True, exist_ok=True)
            
            with open(self.data_path+"/parkings.json", 'w', encoding='utf-8') as f:
                json.dump(parkings, f, ensure_ascii=False, indent=2)
            
            pd.DataFrame(parkings).to_csv(self.data_path+"/parkings.csv", index=False)
            
            
            for p in parkings[:5]:
                print(f"   - {p['name']}")
            
            return parkings
            
        except Exception as e:
            print(f" Erreur: {e}")
            return []

if __name__ == "__main__":
    parkings=parking_factory("../data/osm")
    stations =parkings.get_parkings()
    
    print("\n" + "**" * 30)
    print("  DONNÉES OSM RÉCUPÉRÉES !")
    print("**" * 30)
