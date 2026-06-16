from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth.routes import router as auth_router
from app.config import settings
from app.database import SessionLocal
from app.db_upgrade import ensure_auth_schema
from app.seed import seed_database
from app import routes
from app.routers import conflicts as conflicts_router
from app.routers import sync as sync_router
from app.routers import versions as versions_router
from app.routers import webhooks as webhooks_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_auth_schema()
    db = SessionLocal()
    try:
        seed_database(db)
    finally:
        db.close()
    yield


app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(sync_router.router)
app.include_router(conflicts_router.router)
app.include_router(versions_router.router)
app.include_router(webhooks_router.router)
app.include_router(routes.router)
