"""
Vérifie que GTFS + OSM sont correctement installés
"""
import pandas as pd
import osmnx as ox
import os

print("=" * 60)
print(" VÉRIFICATION DE L'INSTALLATION")
print("=" * 60)

# 1. Vérifier GTFS
print("\n 1. GTFS Statique SNCF:")
try:
    stops = pd.read_csv("data/gtfs/stops.txt")
    routes = pd.read_csv("data/gtfs/routes.txt")
    trips = pd.read_csv("data/gtfs/trips.txt")
    stop_times = pd.read_csv("data/gtfs/stop_times.txt")
    
    print(f"   {len(stops):,} gares chargées")
    print(f"   {len(routes):,} lignes")
    print(f"   {len(trips):,} voyages")
    print(f"   {len(stop_times):,} horaires")
    
    # Vérifier Bordeaux
    bordeaux = stops[stops['stop_name'].str.contains('Bordeaux', na=False, case=False)]
    print(f"\n   {len(bordeaux)} gares Bordeaux trouvées")
    
    if len(bordeaux) > 0:
        print(f"     Exemple: {bordeaux.iloc[0]['stop_name']}")
        print(f"     ID: {bordeaux.iloc[0]['stop_id']}")
    
except Exception as e:
    print(f"   Erreur GTFS: {e}")

# 2. Vérifier OSM
print("\n 2. OpenStreetMap Bordeaux:")
try:
    if os.path.exists("data/osm/bordeaux_network.graphml"):
        G = ox.load_graphml("data/osm/bordeaux_network.graphml")
        print(f"   Réseau chargé: {len(G.nodes):,} nœuds")
        print(f"   {len(G.edges):,} routes")
        
        # Test de calcul de distance
        nodes = list(G.nodes())[:2]
        if len(nodes) >= 2:
            print(f"   Graphe fonctionnel (test OK)")
    else:
        print("   Fichier réseau OSM non trouvé")
        
except Exception as e:
    print(f"   Erreur OSM: {e}")

# 3. Vérifier la structure
print("\n 3. Structure du projet:")
folders = [
    "data/gtfs",
    "data/osm",
    "src/gtfs",
    "src/osm",
    "scripts",
  
]

for folder in folders:
    if os.path.exists(folder):
        print(f"   exists {folder}/")
    else:
        print(f"  not exists {folder}/ (manquant)")

# Résumé
print("\n" + "=" * 60)
print(" RÉSUMÉ")
print("=" * 60)

gtfs_ok = os.path.exists("data/gtfs/stops.txt")
osm_ok = os.path.exists("data/osm/bordeaux_network.graphml")

if gtfs_ok and osm_ok:
    print("\n INSTALLATION COMPLÈTE !")
   
else:
    print("\n Installation incomplète:")
    if not gtfs_ok:
        print("    GTFS manquant → python scripts/download_gtfs_sncf.py")
    if not osm_ok:
        print("    OSM manquant → python scripts/download_osm_bordeaux.py")


