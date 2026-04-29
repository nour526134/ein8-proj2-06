from fastapi import APIRouter, Query
from backend.services.gtfs_service import GTFSService

router = APIRouter(prefix="/trains", tags=["trains"])
gtfs_service = GTFSService(gtfs_dir="data/gtfs")


@router.get("/next")
def get_next_trains(stop_id: str, at_time: str, limit: int = 10):
    df = gtfs_service.get_next_trains(stop_id, current_time=at_time, limit=limit)
    trains = df.to_dict(orient="records") if len(df) > 0 else []
    return {
        "stop_id": stop_id,
        "at_time": at_time,
        "trains": trains
    }

