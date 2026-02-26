"""
Démonstration du service GTFS
Cas d'usage pratiques
"""
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.gtfs_service import GTFSService

def demo_bordeaux():
    """Exemple: Trouver les trains à Bordeaux"""
    
    print("=" * 60)
    print(" DEMO: TRAINS À BORDEAUX SAINT-JEAN")
    print("=" * 60)
    
    # Initialiser le service
    service = GTFSService("data/gtfs")
    
    # Chercher Bordeaux Saint-Jean
    print("\n Recherche 'Bordeaux Saint-Jean'...")
    bordeaux = service.find_station("Bordeaux-Saint-Jean")
    
    if len(bordeaux) == 0:
        print(" Gare non trouvée, essayez juste 'Bordeaux'")
        bordeaux = service.find_station("Bordeaux")
    
    if len(bordeaux) > 0:
        # Prendre la première gare
        stop = bordeaux.iloc[0]
        print(f"\n Gare trouvée:")
        print(f"   Nom: {stop['stop_name']}")
        print(f"   ID: {stop['stop_id']}")
        
        # Afficher les prochains trains à différentes heures
        times = ["06:00:00", "12:00:00", "18:00:00"]
        
        for time in times:
            print(f"\n{'='*60}")
            print(f" Trains après {time}")
            print(f"{'='*60}")
            
            trains = service.get_next_trains(stop['stop_id'], time, limit=3)
            
            if len(trains) > 0:
                print(trains.to_string(index=False))
            else:
                print("   Aucun train trouvé")
    else:
        print(" Aucune gare Bordeaux trouvée")


def demo_comparison():
    """Exemple: Comparer plusieurs gares"""
    
    print("\n" + "=" * 60)
    print("DEMO: COMPARAISON DE GARES")
    print("=" * 60)
    
    service = GTFSService("data/gtfs")
    
    # Chercher plusieurs gares
    cities = ["Paris", "Lyon", "Marseille", "Bordeaux"]
    
    print("\n Nombre de trains après 10:00 dans chaque ville:\n")
    
    for city in cities:
        stations = service.find_station(city)
        
        if len(stations) > 0:
            # Prendre la première gare
            stop_id = stations.iloc[0]['stop_id']
            stop_name = stations.iloc[0]['stop_name']
            
            # Compter les trains
            trains = service.get_next_trains(stop_id, "10:00:00", limit=100)
            
            print(f"  {city:<15} ({stop_name[:30]:<30}): {len(trains)} trains")


if __name__ == "__main__":
    # Démo 1: Bordeaux
    demo_bordeaux()
    
    # Démo 2: Comparaison
    demo_comparison()
    
    print("\n" + "*" * 30)
    print("  Démo terminée !")
    print("*" * 30)
