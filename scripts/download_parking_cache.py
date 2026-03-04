import json
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from parking.parking_service import ParkingServiceOSRM
def main_download_parking_cache():
    service = ParkingServiceOSRM(
        use_public_osrm=True,
        cache_dir="data/cache2",
        profile="walking",   
        rate_limit_s=0.3,
        precompute=True,
    )

main_download_parking_cache()