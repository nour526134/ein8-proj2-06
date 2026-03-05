
"""
Vérifie à quelle heure partent les trains dans le bon et mauvais sens
"""
from src.gtfs_service import GTFSService
import pandas as pd

service = GTFSService("data/gtfs_bordeaux")

print("=" * 80)
print("🔬 HORAIRES DES TRAINS PAR DIRECTION")
print("=" * 80)

origin_id = "StopArea:OCE87491225"
dest_id = "StopArea:OCE87491266"
search_time = "20:18:28"  # De vos logs

print(f"\n📍 Origine: {origin_id}")
print(f"📍 Destination: {dest_id}")
print(f"⏰ Heure de recherche: {search_time}")

origin_stop_ids = service._get_queryable_stop_ids(origin_id)
dest_stop_ids = service._get_queryable_stop_ids(dest_id)

stop_times = service.stop_times_mgr.stop_times

# Trips passant par l'origine
origin_trips = stop_times[stop_times['stop_id'].isin(origin_stop_ids)].copy()

# Trips passant par la destination
dest_trips = stop_times[stop_times['stop_id'].isin(dest_stop_ids)].copy()

# Trips en commun
common_trip_ids = set(origin_trips['trip_id']) & set(dest_trips['trip_id'])

print(f"\n🔗 Total trips en commun: {len(common_trip_ids)}")

# Analyser chaque trip
forward_trains = []   # Bon sens
backward_trains = []  # Mauvais sens

for trip_id in common_trip_ids:
    origin_row = origin_trips[origin_trips['trip_id'] == trip_id].iloc[0]
    dest_row = dest_trips[dest_trips['trip_id'] == trip_id].iloc[0]
    
    origin_seq = origin_row['stop_sequence']
    dest_seq = dest_row['stop_sequence']
    departure = origin_row['departure_time']
    
    if dest_seq > origin_seq:
        # Bon sens
        forward_trains.append({
            'trip_id': trip_id,
            'departure': departure,
            'origin_seq': origin_seq,
            'dest_seq': dest_seq
        })
    else:
        # Mauvais sens
        backward_trains.append({
            'trip_id': trip_id,
            'departure': departure,
            'origin_seq': origin_seq,
            'dest_seq': dest_seq
        })

df_forward = pd.DataFrame(forward_trains).sort_values('departure') if forward_trains else pd.DataFrame()
df_backward = pd.DataFrame(backward_trains).sort_values('departure') if backward_trains else pd.DataFrame()

# ═══════════════════════════════════════════════════════════
# TRAINS DANS LE BON SENS
# ═══════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print(f"✅ TRAINS DANS LE BON SENS ({len(df_forward)} trains)")
print(f"{'='*80}")

if len(df_forward) > 0:
    print(f"\n📊 Horaires de départ:\n")
    
    for i, train in df_forward.iterrows():
        marker = ""
        if train['departure'] >= search_time:
            marker = " ← APRÈS recherche"
        else:
            marker = " (déjà parti)"
        
        print(f"   {train['departure']}{marker}")
    
    # Statistiques
    available_after = df_forward[df_forward['departure'] >= search_time]
    departed_before = df_forward[df_forward['departure'] < search_time]
    
    print(f"\n📈 RÉSUMÉ:")
    print(f"   Total bon sens:           {len(df_forward)}")
    print(f"   Disponibles après {search_time}: {len(available_after)} ✅")
    print(f"   Déjà partis:              {len(departed_before)} ❌")
    
    if len(available_after) > 0:
        next_train = available_after.iloc[0]
        print(f"\n   🚂 Prochain train (bon sens): {next_train['departure']}")
else:
    print("\n❌ Aucun train dans le bon sens")

# ═══════════════════════════════════════════════════════════
# TRAINS DANS LE MAUVAIS SENS
# ═══════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print(f"❌ TRAINS DANS LE MAUVAIS SENS ({len(df_backward)} trains)")
print(f"{'='*80}")

if len(df_backward) > 0:
    print(f"\n📊 Horaires de départ:\n")
    
    for i, train in df_backward.head(10).iterrows():
        marker = ""
        if train['departure'] >= search_time:
            marker = " ← APRÈS recherche"
        else:
            marker = " (déjà parti)"
        
        print(f"   {train['departure']}{marker}")
    
    # Statistiques
    available_after = df_backward[df_backward['departure'] >= search_time]
    
    print(f"\n📈 RÉSUMÉ:")
    print(f"   Total mauvais sens:       {len(df_backward)}")
    print(f"   Disponibles après {search_time}: {len(available_after)}")
    
    if len(available_after) > 0:
        next_train = available_after.iloc[0]
        print(f"\n   🚂 Prochain train (mauvais sens): {next_train['departure']}")

# ═══════════════════════════════════════════════════════════
# CONCLUSION
# ═══════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("💡 CONCLUSION")
print(f"{'='*80}")

forward_available = len(df_forward[df_forward['departure'] >= search_time])
backward_available = len(df_backward[df_backward['departure'] >= search_time])

print(f"\nÀ {search_time}:")

if forward_available > 0:
    print(f"   ✅ {forward_available} trains disponibles dans le BON sens")
    print(f"   → train_wait_time() DEVRAIT en trouver un")
    print(f"\n   🐛 Problème: limit trop petit ?")
    print(f"      Les {forward_available} trains bon sens sont peut-être")
    print(f"      après les 500 premiers trains retournés par get_next_trains()")
else:
    print(f"   ❌ AUCUN train disponible dans le bon sens")
    print(f"   ✅ {backward_available} trains disponibles dans le mauvais sens")
    print(f"\n   🐛 Problème: DÉCALAGE TEMPOREL !")
    print(f"      À 20h00 (reset): trains bon sens disponibles")
    print(f"      À 20h18 (step):  tous partis, reste que mauvais sens")
    print(f"\n   💡 Solution:")
    print(f"      1. Limiter heures de départ (reset avant 18h)")
    print(f"      2. Vérifier train disponible dans reset()")
    print(f"      3. Corriger get_reachable_stations() pour filtrer direction")

print(f"\n{'='*80}")
print("✅ Analyse terminée")
print(f"{'='*80}")
