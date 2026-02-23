from fastapi import FastAPI
from services.api.app.routers.trains import router as trains_router
from services.api.app.routers.decision import router as decision_router





serveur = FastAPI(title="Modal Shift API", version="0.1.0")

@serveur.get("/health")
def health():
    return {"status": "ok"}

serveur.include_router(trains_router)
serveur.include_router(decision_router)