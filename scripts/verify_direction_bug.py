"""
Vérifie que get_reachable_stations() retourne des destinations
dans le MAUVAIS sens (bug de direction)
"""
from src.gtfs_service import GTFSService
import pandas as pd

service = GTFSService("data/gtfs_bordeaux")

print("=" * 80)
print("🔬 VÉRIFICATION DU BUG DE DIRECTION")
print("=" * 80)

# Paire problématique de vos logs
origin_id = "StopArea:OCE87491225"
dest_id = "StopArea:OCE87491266"

print(f"\n📍 Origine: {origin_id}")
print(f"📍 Destination: {dest_id}")

# ═══════════════════════════════════════════════════════════
# ÉTAPE 1 : get_reachable_stations() dit quoi ?
# ═══════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("1️⃣ TEST get_reachable_stations()")
print(f"{'='*80}")

current_time = 20.0  # 20h00 (de vos logs)
print(f"\n⏰ Heure: {current_time}h")

reachable = service.get_reachable_stations(origin_id, current_time, min_trips=1)

print(f"\n✅ Destinations accessibles: {len(reachable)}")

# Vérifier si destination est dans la liste
dest_in_list = dest_id in reachable['destination_station_id'].values

print(f"\n🎯 {dest_id} dans la liste: {dest_in_list}")

if dest_in_list:
    dest_row = reachable[reachable['destination_station_id'] == dest_id].iloc[0]
    print(f"   Nom: {dest_row['destination_station_name']}")
    print(f"   Trips: {dest_row['trip_count']}")
    print(f"   ❌ get_reachable_stations() dit: ACCESSIBLE")
else:
    print(f"   ✅ get_reachable_stations() dit: NON ACCESSIBLE")

# ═══════════════════════════════════════════════════════════
# ÉTAPE 2 : Vérifier MANUELLEMENT tous les trips
# ═══════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("2️⃣ VÉRIFICATION MANUELLE DES TRIPS")
print(f"{'='*80}")

origin_stop_ids = service._get_queryable_stop_ids(origin_id)
dest_stop_ids = service._get_queryable_stop_ids(dest_id)

print(f"\n📋 StopPoints origine: {origin_stop_ids}")
print(f"📋 StopPoints destination: {dest_stop_ids}")

stop_times = service.stop_times_mgr.stop_times

# Trips passant par l'origine
origin_trips = stop_times[stop_times['stop_id'].isin(origin_stop_ids)].copy()
print(f"\n🚂 Trips passant par l'origine: {len(origin_trips)}")

# Trips passant par la destination
dest_trips = stop_times[stop_times['stop_id'].isin(dest_stop_ids)].copy()
print(f"🚂 Trips passant par la destination: {len(dest_trips)}")

# Trips en commun
common_trip_ids = set(origin_trips['trip_id']) & set(dest_trips['trip_id'])
print(f"\n🔗 Trips en commun: {len(common_trip_ids)}")

# ═══════════════════════════════════════════════════════════
# ÉTAPE 3 : Analyser la DIRECTION pour chaque trip
# ═══════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("3️⃣ ANALYSE DE LA DIRECTION")
print(f"{'='*80}")

valid_forward = 0   # Origine → Destination (bon sens)
invalid_backward = 0  # Destination → Origine (mauvais sens)

print(f"\n📊 Analyse de chaque trip:\n")

for trip_id in list(common_trip_ids)[:10]:  # Limiter à 10 pour l'affichage
    # Récupérer les arrêts
    origin_row = origin_trips[origin_trips['trip_id'] == trip_id].iloc[0]
    dest_row = dest_trips[dest_trips['trip_id'] == trip_id].iloc[0]
    
    origin_seq = origin_row['stop_sequence']
    dest_seq = dest_row['stop_sequence']
    
    # Vérifier la direction
    if dest_seq > origin_seq:
        direction = "✅ AVANT (bon sens)"
        valid_forward += 1
    else:
        direction = "❌ ARRIÈRE (mauvais sens)"
        invalid_backward += 1
    
    print(f"   Trip {trip_id[:40]}...")
    print(f"      Origine seq: {origin_seq}")
    print(f"      Dest seq:    {dest_seq}")
    print(f"      Direction:   {direction}")
    print()

# Compter TOUS les trips (pas juste les 10 affichés)
for trip_id in common_trip_ids:
    origin_row = origin_trips[origin_trips['trip_id'] == trip_id].iloc[0]
    dest_row = dest_trips[dest_trips['trip_id'] == trip_id].iloc[0]
    
    if dest_row['stop_sequence'] > origin_row['stop_sequence']:
        valid_forward += 1
    else:
        invalid_backward += 1

# Reset counters (on les a comptés 2 fois)
valid_forward = 0
invalid_backward = 0

for trip_id in common_trip_ids:
    origin_row = origin_trips[origin_trips['trip_id'] == trip_id].iloc[0]
    dest_row = dest_trips[dest_trips['trip_id'] == trip_id].iloc[0]
    
    if dest_row['stop_sequence'] > origin_row['stop_sequence']:
        valid_forward += 1
    else:
        invalid_backward += 1

# ═══════════════════════════════════════════════════════════
# ÉTAPE 4 : CONCLUSION
# ═══════════════════════════════════════════════════════════
print(f"{'='*80}")
print("4️⃣ RÉSUMÉ")
print(f"{'='*80}")

print(f"\n📊 Sur {len(common_trip_ids)} trips en commun:")
print(f"   ✅ Bon sens (Origine → Destination):     {valid_forward}")
print(f"   ❌ Mauvais sens (Destination → Origine): {invalid_backward}")

print(f"\n{'='*80}")
print("💡 CONCLUSION")
print(f"{'='*80}")

if invalid_backward > 0 and valid_forward == 0:
    print(f"\n❌❌❌ BUG CONFIRMÉ !")
    print(f"\n   TOUS les {invalid_backward} trips vont dans le MAUVAIS sens")
    print(f"   (Destination est AVANT origine dans le parcours)")
    print(f"\n   get_reachable_stations() dit: '{dest_id}' accessible")
    print(f"   MAIS c'est FAUX car tous les trains vont dans le sens inverse !")
    print(f"\n   ✅ SOLUTION:")
    print(f"      Dans get_reachable_stations(), filtrer avec:")
    print(f"      stop_sequence > origin_seq")

elif valid_forward > 0:
    print(f"\n✅ Pas de bug de direction")
    print(f"   Il y a {valid_forward} trips dans le bon sens")
    print(f"   Le problème est ailleurs (décalage temporel, limit, etc.)")

else:
    print(f"\n⚠️ Aucun trip en commun")
    print(f"   get_reachable_stations() ne devrait PAS retourner cette destination")

# ══════════════════════════════════════��════════════════════
# ÉTAPE 5 : VISUALISER UN EXEMPLE DE TRIP
# ═══════════════════════════════════════════════════════════
if len(common_trip_ids) > 0:
    print(f"\n{'='*80}")
    print("5️⃣ EXEMPLE DE TRIP")
    print(f"{'='*80}")
    
    example_trip = list(common_trip_ids)[0]
    
    print(f"\nTrip ID: {example_trip}")
    
    # Tous les arrêts
    all_stops = service.get_all_stops_for_trip(example_trip)
    
    print(f"\n🚂 Parcours complet ({len(all_stops)} arrêts):\n")
    
    for i, (_, stop) in enumerate(all_stops.iterrows(), 1):
        marker = ""
        
        if stop['stop_id'] in origin_stop_ids:
            marker = " ← ORIGINE"
        elif stop['stop_id'] in dest_stop_ids:
            marker = " ← DESTINATION"
        
        print(f"   {i:2d}. seq={stop['stop_sequence']:2d} | {stop.get('station_name', stop['stop_name'])[:30]:30s} {marker}")
    
    print(f"\n💡 Observation:")
    
    origin_pos = None
    dest_pos = None
    
    for i, (_, stop) in enumerate(all_stops.iterrows(), 1):
        if stop['stop_id'] in origin_stop_ids:
            origin_pos = i
        if stop['stop_id'] in dest_stop_ids:
            dest_pos = i
    
    if dest_pos and origin_pos:
        if dest_pos < origin_pos:
            print(f"   ❌ DESTINATION (position {dest_pos}) est AVANT ORIGINE (position {origin_pos})")
            print(f"   → Le train passe d'abord par la destination, puis par l'origine")
            print(f"   → Pour aller de origine à destination, il faudrait remonter le temps !")
        else:
            print(f"   ✅ DESTINATION (position {dest_pos}) est APRÈS ORIGINE (position {origin_pos})")
            print(f"   → Direction correcte")

print(f"\n{'='*80}")
print("✅ Vérification terminée")
print(f"{'='*80}")
