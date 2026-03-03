import json
from pathlib import Path
from parking_service import ParkingServiceOSRM
def main():

    # --- charge les données ---
    project_root = Path(__file__).parent.parent
    data_dir = project_root / "data" / "osm"
    parkings_file = data_dir / "parkings.json"
    stations_file = data_dir / "stations.json"

    if not parkings_file.exists() or not stations_file.exists():
        print("❌ Fichiers introuvables:")
        print("  ", parkings_file)
        print("  ", stations_file)
        return

    with open(parkings_file, "r", encoding="utf-8") as f:
        parkings = json.load(f)

    with open(stations_file, "r", encoding="utf-8") as f:
        stations = json.load(f)

    print(f"📊 Chargé: {len(parkings)} parkings, {len(stations)} stations")

    # --- créer le service ---
    service = ParkingServiceOSRM(
        parkings=parkings,
        stations=stations,
        use_public_osrm=True,
        cache_dir="data/cache2",
        profile="walking",   # si souci: "foot"
        rate_limit_s=0.3,
        precompute=True,
    )

    # --- test: afficher 5 stations + parking choisi + temps/distance OSRM ---
    n = min(21, len(stations))
    print("\n=== TEST: meilleur parking (Haversine) + OSRM exact ===")
    for i in range(n):
        s = stations[i]
        sid = s["id"]
        sname = s.get("name", sid)

        best = service.get_best_parking_for_station(sid)
        if not best:
            print(f"\n{i+1}. Station {sname} ({sid}) -> ❌ aucun résultat")
            continue

        print(f"\n{i+1}. Station: {sname} ({sid})")
        print(f"   Parking choisi: {best.get('parking_name', best['parking_id'])} ({best['parking_id']})")
        print(f"   ⏱️  Walk time: {best['walk_time_min']:.1f} min")
        print(f"   📏 Walk dist: {best['walk_distance_m']:.0f} m")

    # --- test bonus: recalcul à la demande sur une station ---
    if stations:
        s = stations[0]
        sid = s["id"]
        best = service.get_best_parking_for_station(sid)
        if best:
            t = service.walk_time_min_parking_to_station(best["parking_id"], sid)
            print("\n=== TEST bonus (recalcul à la demande) ===")
            print(f"Station {sid} / parking {best['parking_id']} -> {t:.1f} min")

    print("\n✅ Test terminé.")


if __name__ == "__main__":
    main()