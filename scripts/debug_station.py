
"""
Debug pourquoi une station spécifique ne retourne pas de trains
"""
from src.gtfs_service import GTFSService
import pandas as pd

service = GTFSService("data/gtfs_bordeaux")

station_id = "StopArea:OCE87584755"

print("=" * 80)
print(f"🔍 DEBUG STATION: {station_id}")
print("=" * 80)

# 1. Vérifier si la station existe
station = service.get_station_by_id(station_id)

if station is None:
    print(f"\n❌ Station {station_id} n'existe PAS dans stops.csv")
else:
    print(f"\n✅ Station trouvée:")
    print(f"   Nom: {station.get('stop_name', 'N/A')}")
    print(f"   Type: {station.get('location_type', 'N/A')}")
    print(f"   Lat/Lon: {station.get('stop_lat')}, {station.get('stop_lon')}")

# 2. Récupérer les StopPoints enfants
print(f"\n{'='*80}")
print("2️⃣ STOPPOINTS ENFANTS")
print(f"{'='*80}")

children = service.stops_mgr.get_stoppoints_for_area(station_id)

if len(children) == 0:
    print(f"❌ Aucun StopPoint enfant pour {station_id}")
else:
    print(f"✅ {len(children)} StopPoints trouvés:")
    for _, child in children.iterrows():
        print(f"   • {child['stop_id']}: {child['stop_name']}")

# 3. Vérifier si ces StopPoints ont des horaires
print(f"\n{'='*80}")
print("3️⃣ HORAIRES DANS STOP_TIMES")
print(f"{'='*80}")

if len(children) > 0:
    child_ids = children['stop_id'].tolist()
    
    stop_times = service.stop_times_mgr.stop_times
    
    for child_id in child_ids:
        count = (stop_times['stop_id'] == child_id).sum()
        print(f"   {child_id}: {count} horaires")
    
    # Total
    total = stop_times['stop_id'].isin(child_ids).sum()
    print(f"\n   ✅ Total horaires pour cette station: {total}")

# 4. Tester get_next_trains
print(f"\n{'='*80}")
print("4️⃣ TEST get_next_trains()")
print(f"{'='*80}")

for test_time in ["06:00:00", "10:00:00", "14:00:00", "18:00:00"]:
    trains = service.get_next_trains(station_id, test_time, limit=5)
    print(f"   {test_time}: {len(trains)} trains trouvés")
    
    if len(trains) > 0:
        print(trains[['departure_time', 'trip_headsign']].head())

# 5. Vérifier si la station est dans load_stops()
print(f"\n{'='*80}")
print("5️⃣ PRÉSENCE DANS load_stops()")
print(f"{'='*80}")

all_stations = service.load_stops(stop_areas_only=True)

if station_id in all_stations:
    print(f"✅ Station présente dans load_stops()")
else:
    print(f"❌ Station ABSENTE de load_stops()")
    print(f"   → Elle sera exclue par le filtrage")

print(f"\n{'='*80}")
print("✅ Diagnostic terminé")
print(f"{'='*80}")
