from fastapi import FastAPI

app = FastAPI(title="Modal Shift API", version="0.1.0")

@app.get("/health")
def health():
    return {"status": "ok"}
