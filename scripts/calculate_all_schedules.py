#!/usr/bin/env python3
"""
Script pour calculer tous les horaires et les temps d'attente des trains
pour toutes les paires origin-destination du réseau GTFS.

Le script génère :
- Un CSV avec les temps d'attente pour chaque (origin, dest, heure) 
- Un CSV avec les horaires de départ pour chaque paire
"""

import pandas as pd
import numpy as np
from pathlib import Path
import sys
from typing import List, Tuple
import json

# Ajouter le répertoire racine au chemin Python
repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root))

from src.gtfs_service import GTFSService


def get_all_station_pairs(service: GTFSService) -> List[Tuple[str, str]]:
    """
    Retourne toutes les paires (origin, destination) possibles
    où destination est accessible depuis origin en un seul trip.
    """
    pairs = set()
    
    stops = service.load_stops()
    for origin_id in stops.keys():
        reachable = service.get_reachable_stations(origin_id)
        if not reachable.empty:
            for _, row in reachable.iterrows():
                dest_id = row["destination_station_id"]
                pairs.add((str(origin_id), str(dest_id)))
    
    return sorted(list(pairs))


def get_departures_for_pair(service: GTFSService, origin_id: str, dest_id: str) -> List[float]:
    """
    Retourne la liste triée de tous les horaires de départ (en minutes depuis minuit)
    pour une paire origin-destination donnée.
    """
    origin_id = str(origin_id)
    dest_id = str(dest_id)
    
    # Récupère les trips communs
    trips_origin = service._stop_to_trips.get(origin_id, set())
    trips_dest = service._stop_to_trips.get(dest_id, set())
    common_trips = trips_origin & trips_dest
    
    if not common_trips:
        return []
    
    st = service._stop_times[service._stop_times["trip_id"].isin(common_trips)].copy()
    
    # Filtre pour les arrêts valides
    origin_rows = st[st["stop_id"] == origin_id][
        ["trip_id", "stop_sequence", "departure_min"]
    ].rename(columns={"stop_sequence": "seq_orig", "departure_min": "dep_orig"})
    
    dest_rows = st[st["stop_id"] == dest_id][
        ["trip_id", "stop_sequence"]
    ].rename(columns={"stop_sequence": "seq_dest"})
    
    merged = origin_rows.merge(dest_rows, on="trip_id")
    valid = merged[merged["seq_dest"] > merged["seq_orig"]].copy()
    
    if valid.empty:
        return []
    
    departures = sorted(valid["dep_orig"].dropna().astype(float).values.tolist())
    return departures


def minutes_to_hhmmss(minutes: float) -> str:
    """Convertit les minutes depuis minuit en format HH:MM:SS."""
    if pd.isna(minutes) or np.isinf(minutes):
        return "N/A"
    
    total_min = int(minutes)
    hours = (total_min // 60) % 24
    mins = total_min % 60
    secs = int((minutes - total_min) * 60)
    
    return f"{hours:02d}:{mins:02d}:{secs:02d}"


def calculate_wait_times_for_pair(
    service: GTFSService, 
    origin_id: str, 
    dest_id: str,
    sampling_interval: int = 15
) -> pd.DataFrame:
    """
    Calcule les temps d'attente pour une paire (origin, dest)
    à différentes heures du jour.
    
    Args:
        service: GTFSService
        origin_id: ID de la station d'origine
        dest_id: ID de la station de destination
        sampling_interval: Intervalle en minutes entre les calculs (défaut: 15)
    
    Returns:
        DataFrame avec colonnes: origin_id, dest_id, time_hhmm, wait_time_min, next_departure_hhmm
    """
    rows = []
    
    # Calcul pour chaque heure (et chaque intervalle)
    for minute_of_day in range(0, 24 * 60, sampling_interval):
        wait_time = service.train_wait_time_from_trips(origin_id, dest_id, float(minute_of_day))
        
        current_time_str = minutes_to_hhmmss(minute_of_day)
        next_dep_time = minute_of_day + wait_time
        
        # Gérer le passage à minuit
        if next_dep_time >= 24 * 60:
            next_dep_time = next_dep_time % (24 * 60)
        
        next_dep_str = minutes_to_hhmmss(next_dep_time)
        
        rows.append({
            "origin_id": origin_id,
            "destination_id": dest_id,
            "current_time": current_time_str,
            "wait_time_minutes": round(wait_time, 2) if not np.isinf(wait_time) else np.inf,
            "next_departure": next_dep_str,
        })
    
    return pd.DataFrame(rows)


def main():
    """Fonction principale."""
    
    # Initialisation
    gtfs_dir = repo_root / "data" / "gtfs_bordeaux"
    if not gtfs_dir.exists():
        gtfs_dir = repo_root / "data" / "gtfs"
    
    if not gtfs_dir.exists():
        print(f"Erreur: aucun répertoire GTFS trouvé dans {repo_root / 'data'}")
        sys.exit(1)
    
    print(f"Chargement du service GTFS depuis {gtfs_dir}...")
    service = GTFSService(gtfs_dir=str(gtfs_dir))
    
    # Récupération de toutes les paires
    print("Récupération de toutes les paires origin-destination...")
    pairs = get_all_station_pairs(service)
    print(f"✓ {len(pairs)} paires trouvées\n")
    
    # Charge les informations sur les stations
    stops_info = service.load_stops()
    
    # === EXPORT 1: CSV avec tous les temps d'attente (échantillonnage toutes les 15 min) ===
    print("Calcul des temps d'attente pour chaque paire...")
    all_wait_times = []
    
    for i, (origin_id, dest_id) in enumerate(pairs):
        if (i + 1) % 50 == 0:
            print(f"  ... {i + 1}/{len(pairs)} paires traitées")
        
        df = calculate_wait_times_for_pair(service, origin_id, dest_id, sampling_interval=15)
        all_wait_times.append(df)
    
    wait_times_df = pd.concat(all_wait_times, ignore_index=True)
    wait_times_file = repo_root / "scripts" / "output_wait_times.csv"
    wait_times_df.to_csv(wait_times_file, index=False)
    print(f"✓ Temps d'attente exportés dans {wait_times_file}\n")
    
    # === EXPORT 2: JSON avec tous les horaires de départ par paire ===
    print("Récupération de tous les horaires de départ...")
    schedules = {}
    
    for i, (origin_id, dest_id) in enumerate(pairs):
        if (i + 1) % 50 == 0:
            print(f"  ... {i + 1}/{len(pairs)} paires traitées")
        
        departures = get_departures_for_pair(service, origin_id, dest_id)
        
        origin_name = stops_info.get(origin_id, {}).get("name", origin_id)
        dest_name = stops_info.get(dest_id, {}).get("name", dest_id)
        
        key = f"{origin_id}→{dest_id}"
        schedules[key] = {
            "origin_id": origin_id,
            "origin_name": origin_name,
            "destination_id": dest_id,
            "destination_name": dest_name,
            "departures_minutes": departures,
            "departures_hhmm": [minutes_to_hhmmss(m) for m in departures],
            "number_of_departures": len(departures),
        }
    
    schedules_file = repo_root / "scripts" / "output_schedules.json"
    with open(schedules_file, "w", encoding="utf-8") as f:
        json.dump(schedules, f, indent=2, ensure_ascii=False)
    print(f"✓ Horaires exportés dans {schedules_file}\n")
    
    # === EXPORT 3: CSV résumé par paire ===
    print("Création d'un résumé par paire...")
    summary_rows = []
    
    for origin_id, dest_id in pairs:
        departures = get_departures_for_pair(service, origin_id, dest_id)
        origin_name = stops_info.get(origin_id, {}).get("name", origin_id)
        dest_name = stops_info.get(dest_id, {}).get("name", dest_id)
        
        if departures:
            first_dep = minutes_to_hhmmss(min(departures))
            last_dep = minutes_to_hhmmss(max(departures))
            avg_interval = (max(departures) - min(departures)) / (len(departures) - 1) if len(departures) > 1 else 0
        else:
            first_dep = "N/A"
            last_dep = "N/A"
            avg_interval = 0
        
        summary_rows.append({
            "origin_id": origin_id,
            "origin_name": origin_name,
            "destination_id": dest_id,
            "destination_name": dest_name,
            "number_of_departures": len(departures),
            "first_departure": first_dep,
            "last_departure": last_dep,
            "average_interval_minutes": round(avg_interval, 2),
        })
    
    summary_df = pd.DataFrame(summary_rows)
    summary_file = repo_root / "scripts" / "output_schedule_summary.csv"
    summary_df.to_csv(summary_file, index=False)
    print(f"✓ Résumé exporté dans {summary_file}\n")
    
    # Affichage de stats
    print("=" * 60)
    print("STATISTIQUES")
    print("=" * 60)
    print(f"Total de paires: {len(pairs)}")
    print(f"Total d'enregistrements de temps d'attente: {len(wait_times_df)}")
    print(f"\nTemps d'attente min: {wait_times_df['wait_time_minutes'].min():.2f} min")
    print(f"Temps d'attente max: {wait_times_df[wait_times_df['wait_time_minutes'] != np.inf]['wait_time_minutes'].max():.2f} min")
    print(f"Temps d'attente moyen: {wait_times_df[wait_times_df['wait_time_minutes'] != np.inf]['wait_time_minutes'].mean():.2f} min")
    print(f"\nPaires sans train: {(wait_times_df['wait_time_minutes'] == np.inf).sum()} lignes")
    print("\n✓ Tous les fichiers ont été générés avec succès!")


if __name__ == "__main__":
    main()
