import os
import sqlite3
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Optional

import psycopg
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from psycopg.rows import dict_row
from pydantic import BaseModel

DATABASE_URL = os.getenv("DATABASE_URL")
SQLITE_DATABASE = "water_level.db"
PH = "%s" if DATABASE_URL else "?"   # SQL placeholder


class Telemetry(BaseModel):
    train_id: str
    timestamp: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    level_mm: float
    level_percent: float
    loop_current_ma: float
    pressure_hpa: float
    temperature_c: float


@contextmanager
def db():
    if DATABASE_URL:
        conn = psycopg.connect(DATABASE_URL, row_factory=dict_row)
    else:
        conn = sqlite3.connect(SQLITE_DATABASE)
        conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_database():
    with db() as conn:
        cur = conn.cursor()
        if DATABASE_URL:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS telemetry (
                    id BIGSERIAL PRIMARY KEY,
                    train_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    latitude DOUBLE PRECISION,
                    longitude DOUBLE PRECISION,
                    level_mm DOUBLE PRECISION NOT NULL,
                    level_percent DOUBLE PRECISION NOT NULL,
                    loop_current_ma DOUBLE PRECISION NOT NULL,
                    pressure_hpa DOUBLE PRECISION NOT NULL,
                    temperature_c DOUBLE PRECISION NOT NULL
                )""")
            # one-time migration for tables created with NOT NULL (safe to repeat)
            cur.execute("ALTER TABLE telemetry ALTER COLUMN latitude DROP NOT NULL")
            cur.execute("ALTER TABLE telemetry ALTER COLUMN longitude DROP NOT NULL")
        else:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS telemetry (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    train_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    latitude REAL,
                    longitude REAL,
                    level_mm REAL NOT NULL,
                    level_percent REAL NOT NULL,
                    loop_current_ma REAL NOT NULL,
                    pressure_hpa REAL NOT NULL,
                    temperature_c REAL NOT NULL
                )""")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_telemetry_train ON telemetry (train_id, id)")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_database()
    yield


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def home():
    return {"message": "Water Level API is running"}


@app.post("/api/v1/telemetry")
def receive_telemetry(data: Telemetry):
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            f"""INSERT INTO telemetry (train_id, timestamp, latitude, longitude,
                    level_mm, level_percent, loop_current_ma, pressure_hpa, temperature_c)
                VALUES ({", ".join([PH] * 9)})
                {"RETURNING id" if DATABASE_URL else ""}""",
            (data.train_id, data.timestamp, data.latitude, data.longitude,
             data.level_mm, data.level_percent, data.loop_current_ma,
             data.pressure_hpa, data.temperature_c),
        )
        record_id = cur.fetchone()["id"] if DATABASE_URL else cur.lastrowid
    return {"status": "received", "record_id": record_id, "data": data}


@app.get("/api/v1/telemetry")
def get_telemetry(
    limit: int = Query(200, ge=1, le=1000),
    train_id: Optional[str] = None,
):
    sql = """SELECT id, train_id, timestamp, latitude, longitude, level_mm,
                    level_percent, loop_current_ma, pressure_hpa, temperature_c
             FROM telemetry"""
    params = []
    if train_id:
        sql += f" WHERE train_id = {PH}"
        params.append(train_id)
    sql += f" ORDER BY id DESC LIMIT {PH}"
    params.append(limit)

    with db() as conn:
        cur = conn.cursor()
        cur.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]


@app.get("/dashboard", include_in_schema=False)
def dashboard():
    return FileResponse(Path(__file__).parent / "dashboard" / "dashboard.html")