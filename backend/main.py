from fastapi import FastAPI
from backend.api.routers.trains import router as trains_router
from backend.api.routers.decision import router as decision_router




app = FastAPI(title="Modal Shift API", version="0.1.0")

@app.get("/health")
def health():
    return {"status": "ok"}

app.include_router(trains_router)
app.include_router(decision_router)
