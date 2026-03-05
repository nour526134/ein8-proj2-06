"""
Prouve le décalage temporel entre reset() et step()
"""
from src.gtfs_service import GTFSService
import pandas as pd

service = GTFSService("data/gtfs_bordeaux")

print("=" * 80)
print("🔬 DIAGNOSTIC DU DÉCALAGE TEMPOREL")
print("=" * 80)

# Scénario du bug
origin_id = "StopArea:OCE87581009"  # Bordeaux (de vos logs)
dest_id = "StopArea:OCE87582734"     # Destination (de vos logs)

print(f"\n📍 Origine: {origin_id}")
print(f"📍 Destination: {dest_id}")

# ═══════════════════════════════════════════════════════════
# ÉTAPE 1 : Ce que fait reset() (simulation initiale)
# ═══════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("1️⃣ SIMULATION reset() - HEURE INITIALE")
print(f"{'='*80}")

initial_hour = 8.0  # 08:00
initial_time_str = "08:00:00"

print(f"\n⏰ Heure de départ du véhicule: {initial_hour}h ({initial_time_str})")

# Ce que fait get_reachable_stations dans reset()
print(f"\n🔍 Appel: get_reachable_stations('{origin_id}', {initial_hour})")

reachable = service.get_reachable_stations(origin_id, initial_hour, min_trips=1)

print(f"\n✅ Résultat: {len(reachable)} destinations accessibles")

# Vérifier si la destination est dans la liste
dest_in_list = dest_id in reachable['destination_station_id'].values

print(f"\n🎯 Destination {dest_id} dans la liste: {dest_in_list}")

if dest_in_list:
    dest_row = reachable[reachable['destination_station_id'] == dest_id].iloc[0]
    print(f"   Nom: {dest_row['destination_station_name']}")
    print(f"   Trips disponibles: {dest_row['trip_count']}")

# ═══════════════════════════════════════════════════════════
# ÉTAPE 2 : LISTER TOUS LES TRAINS vers cette destination
# ═══════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("2️⃣ TOUS LES TRAINS vers la destination")
print(f"{'='*80}")

# Trouver TOUS les trains qui vont de origin vers dest
origin_stop_ids = service._get_queryable_stop_ids(origin_id)
dest_stop_ids = service._get_queryable_stop_ids(dest_id)

print(f"\n📋 StopPoints origine: {len(origin_stop_ids)}")
print(f"📋 StopPoints destination: {len(dest_stop_ids)}")

# Chercher dans stop_times
stop_times = service.stop_times_mgr.stop_times

# Trips passant par l'origine
origin_trips = stop_times[stop_times['stop_id'].isin(origin_stop_ids)].copy()
origin_trips = origin_trips[origin_trips['departure_time'] >= initial_time_str]

print(f"\n🚂 Trips depuis origine après {initial_time_str}: {len(origin_trips)}")

# Parmi ces trips, lesquels passent par la destination ?
valid_trains = []

for _, origin_row in origin_trips.iterrows():
    trip_id = origin_row['trip_id']
    
    # Vérifier si ce trip passe par la destination
    dest_rows = stop_times[
        (stop_times['trip_id'] == trip_id) & 
        (stop_times['stop_id'].isin(dest_stop_ids))
    ]
    
    if len(dest_rows) > 0:
        dest_row = dest_rows.iloc[0]
        
        # Vérifier l'ordre (destination après origine)
        if dest_row['stop_sequence'] > origin_row['stop_sequence']:
            valid_trains.append({
                'trip_id': trip_id,
                'departure_time': origin_row['departure_time'],
                'arrival_time': dest_row['arrival_time'],
                'origin_seq': origin_row['stop_sequence'],
                'dest_seq': dest_row['stop_sequence']
            })

print(f"\n✅ Trains valides trouvés: {len(valid_trains)}")

if len(valid_trains) > 0:
    print(f"\n📊 Liste des trains {origin_id} → {dest_id}:\n")
    
    df_trains = pd.DataFrame(valid_trains)
    df_trains = df_trains.sort_values('departure_time')
    
    for i, train in df_trains.head(10).iterrows():
        print(f"   {train['departure_time']} → {train['arrival_time']} (trip: {train['trip_id'][:30]}...)")
    
    # ═══════════════════════════════════════════════════════════
    # ÉTAPE 3 : SIMULATION step() - HEURE PLUS TARD
    # ═══════════════════════════════════════════════════════════
    print(f"\n{'='*80}")
    print("3️⃣ SIMULATION step() - APRÈS CONDUITE")
    print(f"{'='*80}")
    
    step_time_str = "08:56:12"  # De vos logs
    
    print(f"\n⏰ Heure d'arrivée à la gare (step): {step_time_str}")
    print(f"⏱️ Temps écoulé: ~56 minutes")
    
    # Filtrer les trains encore disponibles
    remaining_trains = df_trains[df_trains['departure_time'] >= step_time_str]
    
    print(f"\n🚂 Trains encore disponibles après {step_time_str}: {len(remaining_trains)}")
    
    if len(remaining_trains) > 0:
        print(f"\n✅ Prochain train:")
        next_train = remaining_trains.iloc[0]
        print(f"   Départ: {next_train['departure_time']}")
        print(f"   Arrivée: {next_train['arrival_time']}")
    else:
        print(f"\n❌ AUCUN train disponible !")
        
        # Montrer les trains qui sont partis
        past_trains = df_trains[df_trains['departure_time'] < step_time_str]
        
        if len(past_trains) > 0:
            print(f"\n⏰ Trains DÉJÀ PARTIS:")
            for i, train in past_trains.iterrows():
                print(f"   ❌ {train['departure_time']} (parti il y a {service._calculate_time_difference(train['departure_time'], step_time_str):.0f} minutes)")
    
    # ═══════════════════════════════════════════════════════════
    # ÉTAPE 4 : APPEL RÉEL train_wait_time()
    # ═══════════════════════════════════════════════════════════
    print(f"\n{'='*80}")
    print("4️⃣ TEST train_wait_time() à 08:56:12")
    print(f"{'='*80}")
    
    result = service.train_wait_time(origin_id, step_time_str, dest_id)
    
    print(f"\n🔍 train_wait_time('{origin_id}', '{step_time_str}', '{dest_id}')")
    
    if result is not None:
        print(f"✅ Résultat: {result:.1f} minutes d'attente")
    else:
        print(f"❌ Résultat: None")
        print(f"\n💡 PREUVE DU DÉCALAGE TEMPOREL:")
        print(f"   1. À 08:00 → get_reachable_stations dit: destination accessible ✅")
        print(f"   2. À 08:56 → train_wait_time dit: aucun train disponible ❌")
        print(f"   3. Cause: Trains partis PENDANT la conduite")
    
    # ═══════════════════════════════════════════════════════════
    # ÉTAPE 5 : SOLUTION
    # ═══════════════════════════════════════════════════════════
    print(f"\n{'='*80}")
    print("5️⃣ SOLUTION")
    print(f"{'='*80}")
    
    print(f"\n❌ PROBLÈME:")
    print(f"   reset() vérifie trains à 08:00")
    print(f"   step() cherche trains à 08:56")
    print(f"   → Décalage de 56 minutes !")
    
    print(f"\n✅ SOLUTION:")
    print(f"   Dans car_simulator.py reset():")
    print(f"   1. Calculer: estimated_arrival = 08:00 + temps_trajet")
    print(f"   2. Utiliser: get_reachable_stations(..., estimated_arrival)")
    print(f"   3. Vérifier: train_wait_time(..., estimated_arrival, ...)")

else:
    print(f"\n❌ AUCUN train direct de {origin_id} vers {dest_id}")
    print(f"   → get_reachable_stations() ne devrait PAS retourner cette destination")
    print(f"   → Possible bug dans get_reachable_stations()")

print(f"\n{'='*80}")
print("✅ Diagnostic terminé")
print(f"{'='*80}")
