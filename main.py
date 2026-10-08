from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()


# Data format received from the water-level station
class Telemetry(BaseModel):
    device_id: str
    timestamp: str
    level_mm: float
    level_percent: float
    loop_current_ma: float
    pressure_hpa: float
    temperature_c: float


# Home / status endpoint
@app.get("/")
def home():
    return {
        "message": "Water Level API is running"
    }


# Telemetry endpoint
@app.post("/api/v1/telemetry")
def receive_telemetry(data: Telemetry):
    return {
        "status": "received",
        "data": data
    }