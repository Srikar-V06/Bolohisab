import os
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator, Literal

from fastapi import FastAPI, HTTPException

from .database import check_database, initialize_database


def create_app(database_path: Path | None = None) -> FastAPI:
    path = database_path or Path(os.environ.get("DATABASE_PATH", "data/bolohisaab.sqlite3"))

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        initialize_database(path)
        yield

    app = FastAPI(title="BoloHisaab API", version="0.1.0", lifespan=lifespan)

    @app.get("/api/health", tags=["health"])
    def health() -> dict[str, Literal["ok", "connected"]]:
        try:
            check_database(path)
        except sqlite3.Error as error:
            raise HTTPException(status_code=503, detail="Database unavailable") from error
        return {"status": "ok", "database": "connected"}

    return app


app = create_app()
