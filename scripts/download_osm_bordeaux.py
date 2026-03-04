"""
Télécharge le réseau routier de Bordeaux depuis OpenStreetMap
"""
import osmnx as ox
from pathlib import Path
import os

def download_bordeaux_osm():
    """Télécharge le réseau routier de Bordeaux"""
    
    print("=" * 60)
    print(" TÉLÉCHARGEMENT RÉSEAU OSM BORDEAUX")
    print("=" * 60)
    
    # Créer le dossier
    Path("data/osm").mkdir(parents=True, exist_ok=True)
    
    print("\n Zone: Bordeaux Métropole, France")
    print(" Téléchargement en cours (2-5 minutes)...\n")
    
    try:
        # Télécharger le réseau routier
        G = ox.graph_from_place(
            "Bordeaux Métropole, France",
            network_type='drive',
            simplify=True
        )
        
        print(f" Réseau téléchargé:")
        print(f"   - Nœuds (intersections): {len(G.nodes):,}")
        print(f"   - Arêtes (routes): {len(G.edges):,}")
        
        # Sauvegarder
        output_path = "data/osm/bordeaux_network.graphml"
        ox.save_graphml(G, output_path)
        
        file_size = os.path.getsize(output_path) / (1024 * 1024)
        
        print(f"\n Sauvegardé: {output_path}")
        print(f"   Taille: {file_size:.1f} MB")
        
        # Créer une visualisation
        print("\n Création d'une carte...")
        fig, ax = ox.plot_graph(
            G,
            node_size=0,
            edge_linewidth=0.5,
            edge_color='#999999',
            bgcolor='white',
            show=False,
            close=False,
            save=True,
            filepath='data/osm/bordeaux_network.png',
            dpi=150
        )
        
        print(" Carte sauvegardée: data/osm/bordeaux_network.png")
        
        print("\n" + "*" * 30)
        print("  RÉSEAU OSM BORDEAUX INSTALLÉ !")
       
        
        return True
        
    except Exception as e:
        print(f"\n Erreur: {e}")
        return False

def main_download_osm_graph():
    success = download_bordeaux_osm()
    
    if success:
        print("\n PROCHAINE ÉTAPE:")
        
    else:
        print("\n Réessayez ou vérifiez votre connexion")


