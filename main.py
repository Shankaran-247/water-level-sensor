```python
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
PH = "%s" if DATABASE_URL else "?"


# ============================================================
# TELEMETRY MODEL
# ============================================================

class Telemetry(BaseModel):
    train_id: str
    timestamp: str

    latitude: Optional[float] = None
    longitude: Optional[float] = None

    level_mm: float
    level_percent: float
    volume_litres: float

    # Optional for compatibility with new and older firmware
    loop_current_ma: Optional[float] = None

    pressure_hpa: Optional[float] = None
    temperature_c: Optional[float] = None


# ============================================================
# DATABASE CONNECTION
# ============================================================

@contextmanager
def db():
    if DATABASE_URL:
        conn = psycopg.connect(
            DATABASE_URL,
            row_factory=dict_row
        )
    else:
        conn = sqlite3.connect(SQLITE_DATABASE)
        conn.row_factory = sqlite3.Row

    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# ============================================================
# DATABASE INITIALIZATION AND MIGRATION
# ============================================================

def init_database():

    with db() as conn:
        cur = conn.cursor()

        if DATABASE_URL:

            # PostgreSQL
            cur.execute("""
                CREATE TABLE IF NOT EXISTS telemetry (
                    id BIGSERIAL PRIMARY KEY,
                    train_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    latitude DOUBLE PRECISION,
                    longitude DOUBLE PRECISION,
                    level_mm DOUBLE PRECISION NOT NULL,
                    level_percent DOUBLE PRECISION NOT NULL,
                    volume_litres DOUBLE PRECISION NOT NULL,
                    loop_current_ma DOUBLE PRECISION,
                    pressure_hpa DOUBLE PRECISION,
                    temperature_c DOUBLE PRECISION
                )
            """)

            # Migrate existing PostgreSQL databases
            cur.execute("""
                ALTER TABLE telemetry
                ADD COLUMN IF NOT EXISTS volume_litres DOUBLE PRECISION
            """)

            cur.execute("""
                ALTER TABLE telemetry
                ALTER COLUMN latitude DROP NOT NULL
            """)

            cur.execute("""
                ALTER TABLE telemetry
                ALTER COLUMN longitude DROP NOT NULL
            """)

            cur.execute("""
                ALTER TABLE telemetry
                ALTER COLUMN loop_current_ma DROP NOT NULL
            """)

            cur.execute("""
                ALTER TABLE telemetry
                ALTER COLUMN pressure_hpa DROP NOT NULL
            """)

            cur.execute("""
                ALTER TABLE telemetry
                ALTER COLUMN temperature_c DROP NOT NULL
            """)

        else:

            # SQLite
            cur.execute("""
                CREATE TABLE IF NOT EXISTS telemetry (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    train_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    latitude REAL,
                    longitude REAL,
                    level_mm REAL NOT NULL,
                    level_percent REAL NOT NULL,
                    volume_litres REAL,
                    loop_current_ma REAL,
                    pressure_hpa REAL,
                    temperature_c REAL
                )
            """)

            # Check existing SQLite columns
            cur.execute("PRAGMA table_info(telemetry)")
            columns = {
                row["name"]: row
                for row in cur.fetchall()
            }

            # Add volume_litres if missing
            if "volume_litres" not in columns:
                cur.execute("""
                    ALTER TABLE telemetry
                    ADD COLUMN volume_litres REAL
                """)

            # SQLite cannot directly DROP NOT NULL.
            # Rebuild the table if old columns have NOT NULL constraints.
            nullable_columns = [
                "latitude",
                "longitude",
                "loop_current_ma",
                "pressure_hpa",
                "temperature_c"
            ]

            needs_rebuild = any(
                columns.get(name, {}).get("notnull", 0)
                for name in nullable_columns
            )

            if needs_rebuild:

                cur.execute("""
                    CREATE TABLE telemetry_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        train_id TEXT NOT NULL,
                        timestamp TEXT NOT NULL,
                        latitude REAL,
                        longitude REAL,
                        level_mm REAL NOT NULL,
                        level_percent REAL NOT NULL,
                        volume_litres REAL,
                        loop_current_ma REAL,
                        pressure_hpa REAL,
                        temperature_c REAL
                    )
                """)

                cur.execute("""
                    INSERT INTO telemetry_new (
                        id, train_id, timestamp,
                        latitude, longitude,
                        level_mm, level_percent,
                        volume_litres, loop_current_ma,
                        pressure_hpa, temperature_c
                    )
                    SELECT
                        id, train_id, timestamp,
                        latitude, longitude,
                        level_mm, level_percent,
                        volume_litres, loop_current_ma,
                        pressure_hpa, temperature_c
                    FROM telemetry
                """)

                cur.execute("DROP TABLE telemetry")
                cur.execute("""
                    ALTER TABLE telemetry_new
                    RENAME TO telemetry
                """)

        # Index for faster train-specific queries
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_telemetry_train
            ON telemetry (train_id, id)
        """)


# ============================================================
# FASTAPI APPLICATION
# ============================================================

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


# ============================================================
# ROOT ENDPOINT
# ============================================================

@app.get("/")
def home():
    return {
        "message": "Water Level API is running"
    }


# ============================================================
# RECEIVE TELEMETRY
# POST /api/v1/telemetry
# ============================================================

@app.post("/api/v1/telemetry")
def receive_telemetry(data: Telemetry):

    with db() as conn:
        cur = conn.cursor()

        cur.execute(
            f"""
            INSERT INTO telemetry (
                train_id,
                timestamp,
                latitude,
                longitude,
                level_mm,
                level_percent,
                volume_litres,
                loop_current_ma,
                pressure_hpa,
                temperature_c
            )
            VALUES ({", ".join([PH] * 10)})
            {"RETURNING id" if DATABASE_URL else ""}
            """,
            (
                data.train_id,
                data.timestamp,
                data.latitude,
                data.longitude,
                data.level_mm,
                data.level_percent,
                data.volume_litres,
                data.loop_current_ma,
                data.pressure_hpa,
                data.temperature_c
            )
        )

        record_id = (
            cur.fetchone()["id"]
            if DATABASE_URL
            else cur.lastrowid
        )

    return {
        "status": "received",
        "record_id": record_id,
        "data": data
    }


# ============================================================
# GET TELEMETRY
# GET /api/v1/telemetry
# ============================================================

@app.get("/api/v1/telemetry")
def get_telemetry(
    limit: int = Query(200, ge=1, le=1000),
    train_id: Optional[str] = None
):

    sql = """
        SELECT
            id,
            train_id,
            timestamp,
            latitude,
            longitude,
            level_mm,
            level_percent,
            volume_litres,
            loop_current_ma,
            pressure_hpa,
            temperature_c
        FROM telemetry
    """

    params = []

    if train_id:
        sql += f" WHERE train_id = {PH}"
        params.append(train_id)

    sql += f" ORDER BY id DESC LIMIT {PH}"
    params.append(limit)

    with db() as conn:
        cur = conn.cursor()
        cur.execute(sql, params)

        return [
            dict(row)
            for row in cur.fetchall()
        ]


# ============================================================
# DASHBOARD
# ============================================================

@app.get("/dashboard", include_in_schema=False)
def dashboard():

    return FileResponse(
        Path(__file__).parent
        / "dashboard"
        / "dashboard.html"
    )
```
