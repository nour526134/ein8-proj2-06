from fastapi import APIRouter, Query
from services.api.app.services.gtfs_service import GTFSService

router = APIRouter(prefix="/trains", tags=["trains"])
gtfs = GTFSService()

@router.get("/next")
def get_next_trains(stop_id: str, at_time: str = Query(...), limit: int = 10):
    return {
        "stop_id": stop_id,
        "at_time": at_time,
        "trains": gtfs.next_trains(stop_id, at_time, limit),
    }

