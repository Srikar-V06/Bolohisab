import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from threading import Thread
from typing import AsyncIterator, Literal

from fastapi import FastAPI, HTTPException

from .customers import router as customer_router
from .database import check_database, database_path as configured_database_path, initialize_database
from .local_model import LocalModelAdapter, configured_model
from .receipts import public_receipt_origin, router as receipt_router
from .voice import router as voice_router


def create_app(database_path: Path | None = None, local_model: LocalModelAdapter | None = None) -> FastAPI:
    path = database_path or configured_database_path()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        initialize_database(path)
        if local_model is not None:
            # Load the model in the background so the first spoken entry isn't slow.
            Thread(target=local_model.warm, daemon=True).start()
        yield

    app = FastAPI(title="BoloHisaab API", version="0.1.0", lifespan=lifespan)
    app.state.database_path = path
    app.state.local_model = local_model
    app.state.public_receipt_origin = public_receipt_origin()
    app.include_router(customer_router)
    app.include_router(voice_router)
    app.include_router(receipt_router)

    @app.get("/api/health", tags=["health"])
    def health() -> dict[str, Literal["ok", "connected"]]:
        try:
            check_database(path)
        except sqlite3.Error as error:
            raise HTTPException(status_code=503, detail="Database unavailable") from error
        return {"status": "ok", "database": "connected"}

    return app


app = create_app(local_model=configured_model())
