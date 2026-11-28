import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from threading import Thread
from time import time
from typing import AsyncIterator, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .auth import auth_config, router as auth_router
from .customers import router as customer_router
from .customer_portal import router as portal_router
from .invitations import router as invitation_router
from .reports import router as report_router
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
    app.state.auth_config = config = auth_config()
    app.state.auth_clock = lambda: int(time())
    app.add_middleware(CORSMiddleware, allow_origins=config.origins, allow_credentials=True,
                       allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
                       allow_headers=["Content-Type", "X-CSRF-Token"], expose_headers=["Retry-After"])
    app.include_router(auth_router)
    app.include_router(customer_router)
    app.include_router(voice_router)
    app.include_router(receipt_router)
    app.include_router(invitation_router)
    app.include_router(portal_router)
    app.include_router(report_router)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError):
        if request.url.path.startswith("/api/auth/"):
            # Pydantic validation details can otherwise echo input, including raw passwords.
            return JSONResponse({"detail": "INVALID_AUTH_INPUT"}, status_code=422)
        return await request_validation_exception_handler(request, error)

    @app.get("/api/health", tags=["health"])
    def health() -> dict[str, Literal["ok", "connected"]]:
        try:
            check_database(path)
        except sqlite3.Error as error:
            raise HTTPException(status_code=503, detail="Database unavailable") from error
        return {"status": "ok", "database": "connected"}

    return app


app = create_app(local_model=configured_model())
