import json
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from parking.parking_service import ParkingServiceStatic
def main_download_parking_cache():
    service = ParkingServiceStatic()

main_download_parking_cache()