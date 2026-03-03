import json
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from parking.parking_service import ParkingServiceOSRM
def main_download_parking_cache():

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
        use_public_osrm=True,
        cache_dir="data/cache2",
        profile="walking",   # si souci: "foot"
        rate_limit_s=0.3,
        precompute=True,
    )

main_download_parking_cache()