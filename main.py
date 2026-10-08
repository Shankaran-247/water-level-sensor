from fastapi import FastAPI
from pydantic import BaseModel
import sqlite3


app = FastAPI()

DATABASE = "water_level.db"


# -----------------------------
# Data received from train
# -----------------------------
class Telemetry(BaseModel):
    train_id: str
    timestamp: str
    latitude: float
    longitude: float
    level_mm: float
    level_percent: float
    loop_current_ma: float
    pressure_hpa: float
    temperature_c: float


# -----------------------------
# Create database/table
# -----------------------------
def init_database():
    connection = sqlite3.connect(DATABASE)
    cursor = connection.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS telemetry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            train_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            level_mm REAL NOT NULL,
            level_percent REAL NOT NULL,
            loop_current_ma REAL NOT NULL,
            pressure_hpa REAL NOT NULL,
            temperature_c REAL NOT NULL
        )
    """)

    connection.commit()
    connection.close()


# Create database when API starts
@app.on_event("startup")
def startup():
    init_database()


# -----------------------------
# Home endpoint
# -----------------------------
@app.get("/")
def home():
    return {
        "message": "Water Level API is running"
    }


# -----------------------------
# Receive train telemetry
# -----------------------------
@app.post("/api/v1/telemetry")
def receive_telemetry(data: Telemetry):

    connection = sqlite3.connect(DATABASE)
    cursor = connection.cursor()

    cursor.execute("""
        INSERT INTO telemetry (
            train_id,
            timestamp,
            latitude,
            longitude,
            level_mm,
            level_percent,
            loop_current_ma,
            pressure_hpa,
            temperature_c
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data.train_id,
        data.timestamp,
        data.latitude,
        data.longitude,
        data.level_mm,
        data.level_percent,
        data.loop_current_ma,
        data.pressure_hpa,
        data.temperature_c
    ))

    connection.commit()

    record_id = cursor.lastrowid

    connection.close()

    return {
        "status": "received",
        "record_id": record_id,
        "data": data
    }


# -----------------------------
# Get all telemetry records
# -----------------------------
@app.get("/api/v1/telemetry")
def get_telemetry():

    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            id,
            train_id,
            timestamp,
            latitude,
            longitude,
            level_mm,
            level_percent,
            loop_current_ma,
            pressure_hpa,
            temperature_c
        FROM telemetry
        ORDER BY id DESC
    """)

    records = cursor.fetchall()

    connection.close()

    return [dict(record) for record in records]