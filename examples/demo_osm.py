
"""
Démonstration OSM
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from src.osm.itinerary_manager import ItineraryManager

def demo_routes():
    print("=" * 60)
    print(" DEMO: CALCUL D'ITINÉRAIRES")
    print("=" * 60)
    
    rm = ItineraryManager()
    
    station = (44.8261, -0.5556)  # Bordeaux Saint-Jean
    
    locations = {
        "Mériadeck": (44.8500, -0.5700),
        "Chartrons": (44.8550, -0.5720),
        "Bastide": (44.8350, -0.5450),
        "Pessac": (44.8000, -0.6300)
    }
    
    print(f"\n Destination: Bordeaux Saint-Jean\n")
    
    for name, pos in locations.items():
        route = rm.calculate_route(*pos, *station)
        print(f" {name:<15} : {route['distance_km']:5.1f} km ({route['duration_minutes']:4.1f} min)")

if __name__ == "__main__":
    demo_routes()
