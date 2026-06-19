from fastapi import FastAPI
from app.config import ENV

app = FastAPI(title="crux", version="0.1.0")


@app.get("/healthz")
def healthz():
    return {"status": "ok", "env": ENV}
