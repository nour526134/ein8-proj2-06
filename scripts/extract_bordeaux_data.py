"""
Extrait uniquement les données GTFS concernant Bordeaux Métropole
Crée un nouveau dataset GTFS filtré dans data/gtfs_bordeaux/
"""

import pandas as pd
from pathlib import Path
import shutil
from math import radians, cos, sin, sqrt, atan2

def haversine_km(lat1, lon1, lat2, lon2):
    """Calcule la distance haversine en km"""
    R = 6371.0  # Rayon de la Terre en km
    
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    
    return R * c


def extract_bordeaux_gtfs(
    input_dir="data/gtfs",
    output_dir="data/gtfs_bordeaux",
    center_lat=44.8378,  # Bordeaux Saint-Jean
    center_lon=-0.5792,
    radius_km=30.0  # Rayon autour de Bordeaux
):
    """
    Extrait les données GTFS pour Bordeaux Métropole
    
    Args:
        input_dir: Dossier GTFS source
        output_dir: Dossier GTFS de sortie
        center_lat: Latitude du centre (Bordeaux Saint-Jean)
        center_lon: Longitude du centre
        radius_km: Rayon de recherche en km
    """
    
    print("=" * 80)
    print("📊 EXTRACTION DONNÉES BORDEAUX MÉTROPOLE")
    print("=" * 80)
    
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    
    # Créer le dossier de sortie
    output_path.mkdir(parents=True, exist_ok=True)
    
    print(f"\n📂 Dossiers:")
    print(f"   Source: {input_path}")
    print(f"   Destination: {output_path}")
    print(f"\n🎯 Zone de recherche:")
    print(f"   Centre: ({center_lat:.4f}, {center_lon:.4f})")
    print(f"   Rayon: {radius_km} km")
    
    # ==========================================
    # 1. FILTRER LES STOPS (GARES)
    # ==========================================
    print(f"\n{'='*80}")
    print("1️⃣ FILTRAGE DES GARES")
    print(f"{'='*80}")
    
    # Charger stops
    for ext in ['.csv', '.txt']:
        stops_file = input_path / f"stops{ext}"
        if stops_file.exists():
            print(f"\n📂 Chargement {stops_file.name}...")
            stops = pd.read_csv(stops_file)
            break
    else:
        print("❌ Fichier stops non trouvé")
        return
    
    print(f"   Total gares: {len(stops):,}")
    
    # Filtrer par distance
    stops['distance_km'] = stops.apply(
        lambda row: haversine_km(center_lat, center_lon, row['stop_lat'], row['stop_lon'])
        if pd.notna(row['stop_lat']) and pd.notna(row['stop_lon'])
        else 999,
        axis=1
    )
    
    bordeaux_stops = stops[stops['distance_km'] <= radius_km].copy()
    
    print(f"\n✅ Gares dans Bordeaux Métropole: {len(bordeaux_stops):,}")
    print(f"\n   Top 10 gares les plus proches:")
    
    top_stops = bordeaux_stops.nsmallest(10, 'distance_km')
    for _, stop in top_stops.iterrows():
        print(f"      • {stop['stop_name']:<50} {stop['distance_km']:.1f} km")
    
    # Exporter stops
    bordeaux_stops_export = bordeaux_stops.drop(columns=['distance_km'])
    output_stops = output_path / f"stops{ext}"
    bordeaux_stops_export.to_csv(output_stops, index=False)
    print(f"\n💾 Exporté: {output_stops}")
    
    # Liste des stop_ids de Bordeaux
    bordeaux_stop_ids = set(bordeaux_stops['stop_id'])
    
    # ==========================================
    # 2. FILTRER LES STOP_TIMES
    # ==========================================
    print(f"\n{'='*80}")
    print("2️⃣ FILTRAGE DES HORAIRES (stop_times)")
    print(f"{'='*80}")
    
    for ext in ['.csv', '.txt']:
        stop_times_file = input_path / f"stop_times{ext}"
        if stop_times_file.exists():
            print(f"\n📂 Chargement {stop_times_file.name}...")
            stop_times = pd.read_csv(stop_times_file)
            break
    else:
        print("❌ Fichier stop_times non trouvé")
        return
    
    print(f"   Total horaires: {len(stop_times):,}")
    
    # Filtrer stop_times pour Bordeaux
    bordeaux_stop_times = stop_times[stop_times['stop_id'].isin(bordeaux_stop_ids)].copy()
    
    print(f"✅ Horaires Bordeaux: {len(bordeaux_stop_times):,}")
    
    # Exporter stop_times
    output_stop_times = output_path / f"stop_times{ext}"
    bordeaux_stop_times.to_csv(output_stop_times, index=False)
    print(f"💾 Exporté: {output_stop_times}")
    
    # Liste des trip_ids concernés
    bordeaux_trip_ids = set(bordeaux_stop_times['trip_id'])
    print(f"\n📊 Trips concernés: {len(bordeaux_trip_ids):,}")
    
    # ==========================================
    # 3. FILTRER LES TRIPS
    # ==========================================
    print(f"\n{'='*80}")
    print("3️⃣ FILTRAGE DES VOYAGES (trips)")
    print(f"{'='*80}")
    
    for ext in ['.csv', '.txt']:
        trips_file = input_path / f"trips{ext}"
        if trips_file.exists():
            print(f"\n📂 Chargement {trips_file.name}...")
            trips = pd.read_csv(trips_file)
            break
    else:
        print("❌ Fichier trips non trouvé")
        return
    
    print(f"   Total trips: {len(trips):,}")
    
    # Filtrer trips
    bordeaux_trips = trips[trips['trip_id'].isin(bordeaux_trip_ids)].copy()
    
    print(f"✅ Trips Bordeaux: {len(bordeaux_trips):,}")
    
    # Exporter trips
    output_trips = output_path / f"trips{ext}"
    bordeaux_trips.to_csv(output_trips, index=False)
    print(f"💾 Exporté: {output_trips}")
    
    # Liste des route_ids concernés
    bordeaux_route_ids = set(bordeaux_trips['route_id'])
    print(f"\n📊 Routes concernées: {len(bordeaux_route_ids):,}")
    
    # ==========================================
    # 4. FILTRER LES ROUTES
    # ==========================================
    print(f"\n{'='*80}")
    print("4️⃣ FILTRAGE DES LIGNES (routes)")
    print(f"{'='*80}")
    
    for ext in ['.csv', '.txt']:
        routes_file = input_path / f"routes{ext}"
        if routes_file.exists():
            print(f"\n📂 Chargement {routes_file.name}...")
            routes = pd.read_csv(routes_file)
            break
    else:
        print("❌ Fichier routes non trouvé")
        return
    
    print(f"   Total routes: {len(routes):,}")
    
    # Filtrer routes
    bordeaux_routes = routes[routes['route_id'].isin(bordeaux_route_ids)].copy()
    
    print(f"✅ Routes Bordeaux: {len(bordeaux_routes):,}")
    
    # Exporter routes
    output_routes = output_path / f"routes{ext}"
    bordeaux_routes.to_csv(output_routes, index=False)
    print(f"💾 Exporté: {output_routes}")
    
    # ==========================================
    # 5. COPIER CALENDAR_DATES
    # ==========================================
    print(f"\n{'='*80}")
    print("5️⃣ CALENDRIER")
    print(f"{'='*80}")
    
    for ext in ['.csv', '.txt']:
        calendar_file = input_path / f"calendar_dates{ext}"
        if calendar_file.exists():
            print(f"\n📂 Copie {calendar_file.name}...")
            
            # Charger calendar_dates
            calendar_dates = pd.read_csv(calendar_file)
            print(f"   Total dates: {len(calendar_dates):,}")
            
            # Filtrer par service_id des trips
            service_ids = set(bordeaux_trips['service_id']) if 'service_id' in bordeaux_trips.columns else set()
            
            if len(service_ids) > 0:
                bordeaux_calendar = calendar_dates[calendar_dates['service_id'].isin(service_ids)].copy()
                print(f"✅ Dates Bordeaux: {len(bordeaux_calendar):,}")
            else:
                # Copier tout le calendrier si pas de service_id
                bordeaux_calendar = calendar_dates.copy()
                print(f"✅ Calendrier complet copié")
            
            # Exporter
            output_calendar = output_path / f"calendar_dates{ext}"
            bordeaux_calendar.to_csv(output_calendar, index=False)
            print(f"💾 Exporté: {output_calendar}")
            break
    
    # ==========================================
    # 6. COPIER AGENCY (si existe)
    # ==========================================
    print(f"\n{'='*80}")
    print("6️⃣ AGENCES (optionnel)")
    print(f"{'='*80}")
    
    for ext in ['.csv', '.txt']:
        agency_file = input_path / f"agency{ext}"
        if agency_file.exists():
            print(f"\n📂 Copie {agency_file.name}...")
            shutil.copy2(agency_file, output_path / f"agency{ext}")
            print(f"✅ Copié")
            break
    
    # ==========================================
    # RÉSUMÉ
    # ==========================================
    print(f"\n{'='*80}")
    print("📊 RÉSUMÉ DE L'EXTRACTION")
    print(f"{'='*80}")
    
    summary = {
        "Gares": len(bordeaux_stops),
        "Horaires": len(bordeaux_stop_times),
        "Trips": len(bordeaux_trips),
        "Routes": len(bordeaux_routes),
    }
    
    for label, count in summary.items():
        print(f"   {label:<20} {count:>10,}")
    
    # Calculer la réduction
    original_stops = len(stops)
    reduction = (1 - len(bordeaux_stops) / original_stops) * 100
    
    print(f"\n💡 Réduction:")
    print(f"   Gares: {original_stops:,} → {len(bordeaux_stops):,} ({reduction:.1f}% réduit)")
    
    print(f"\n✅ Extraction terminée !")
    print(f"📂 Données disponibles dans: {output_path}")
    
    return output_path


def create_readme(output_dir):
    """Crée un README dans le dossier de sortie"""
    
    readme_path = Path(output_dir) / "README.md"
    
    # ✅ CORRECTION: Utiliser liste de lignes
    lines = [
        "# GTFS Bordeaux Metropole",
        "",
        "## Dataset filtre",
        "",
        "Ce dossier contient les donnees GTFS filtrees pour Bordeaux Metropole.",
        "",
        "### Zone geographique",
        "- Centre: Bordeaux Saint-Jean (44.8378, -0.5792)",
        "- Rayon: 30 km",
        "",
        "### Fichiers inclus",
        "- stops.csv : Gares dans la zone",
        "- stop_times.csv : Horaires des trains",
        "- trips.csv : Voyages",
        "- routes.csv : Lignes",
        "- calendar_dates.csv : Calendrier",
        "- agency.csv : Agences (si disponible)",
        "",
        "### Utilisation",
        "",
        "```python",
        "from src.gtfs_service import GTFSService",
        "",
        "service = GTFSService('data/gtfs_bordeaux')",
        "bordeaux = service.find_station('Bordeaux')",
        "```",
        "",
        "### Generation",
        "",
        "Dataset genere avec:",
        "```",
        "python scripts/extract_bordeaux_data.py",
        "```",
        "",
        "Pour changer le rayon:",
        "```",
        "python scripts/extract_bordeaux_data.py --radius 50",
        "```",
    ]
    
    content = "\n".join(lines)
    
    with open(readme_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"\n📝 README créé: {readme_path}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Extrait donnees GTFS Bordeaux Metropole")
    parser.add_argument('--input', default='data/gtfs', help='Dossier GTFS source')
    parser.add_argument('--output', default='data/gtfs_bordeaux', help='Dossier de sortie')
    parser.add_argument('--radius', type=float, default=30.0, help='Rayon en km')
    parser.add_argument('--lat', type=float, default=44.8378, help='Latitude centre')
    parser.add_argument('--lon', type=float, default=-0.5792, help='Longitude centre')
    
    args = parser.parse_args()
    
    # Extraction
    output_path = extract_bordeaux_gtfs(
        input_dir=args.input,
        output_dir=args.output,
        center_lat=args.lat,
        center_lon=args.lon,
        radius_km=args.radius
    )
    
    # Créer README
    if output_path:
        create_readme(output_path)
    
    print("\n" + "=" * 80)
    print("✅ EXTRACTION TERMINÉE")
    print("=" * 80)