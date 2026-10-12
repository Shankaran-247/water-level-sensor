from fastapi import FastAPI
from pydantic import BaseModel
import os
import sqlite3
import psycopg
from psycopg.rows import dict_row

app = FastAPI()

DATABASE_URL = os.getenv("DATABASE_URL")
SQLITE_DATABASE = "water_level.db"


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
# Database connection
# -----------------------------
def get_connection():
    if DATABASE_URL:
        return psycopg.connect(DATABASE_URL, row_factory=dict_row)

    return sqlite3.connect(SQLITE_DATABASE)


# -----------------------------
# Create database/table
# -----------------------------
def init_database():
    connection = get_connection()
    cursor = connection.cursor()

    if DATABASE_URL:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS telemetry (
                id BIGSERIAL PRIMARY KEY,
                train_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                latitude DOUBLE PRECISION NOT NULL,
                longitude DOUBLE PRECISION NOT NULL,
                level_mm DOUBLE PRECISION NOT NULL,
                level_percent DOUBLE PRECISION NOT NULL,
                loop_current_ma DOUBLE PRECISION NOT NULL,
                pressure_hpa DOUBLE PRECISION NOT NULL,
                temperature_c DOUBLE PRECISION NOT NULL
            )
        """)
    else:
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


@app.on_event("startup")
def startup():
    init_database()


# -----------------------------
# Home endpoint
# -----------------------------
@app.get("/")
def home():
    return {"message": "Water Level API is running"}


# -----------------------------
# Receive train telemetry
# -----------------------------
@app.post("/api/v1/telemetry")
def receive_telemetry(data: Telemetry):
    connection = get_connection()
    cursor = connection.cursor()

    placeholders = (
        "%s, %s, %s, %s, %s, %s, %s, %s, %s"
        if DATABASE_URL
        else "?, ?, ?, ?, ?, ?, ?, ?, ?"
    )

    cursor.execute(f"""
        INSERT INTO telemetry (
            train_id, timestamp, latitude, longitude, level_mm,
            level_percent, loop_current_ma, pressure_hpa, temperature_c
        )
        VALUES ({placeholders})
        {"RETURNING id" if DATABASE_URL else ""}
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

    if DATABASE_URL:
        record_id = cursor.fetchone()["id"]
    else:
        record_id = cursor.lastrowid

    connection.commit()
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
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT id, train_id, timestamp, latitude, longitude, level_mm,
               level_percent, loop_current_ma, pressure_hpa, temperature_c
        FROM telemetry
        ORDER BY id DESC
    """)

    records = cursor.fetchall()
    connection.close()

    if DATABASE_URL:
        return records

    return [dict(zip(
        ["id", "train_id", "timestamp", "latitude", "longitude",
         "level_mm", "level_percent", "loop_current_ma",
         "pressure_hpa", "temperature_c"],
        record
    )) for record in records]