from contextlib import asynccontextmanager

from fastapi import FastAPI

from .config import settings
from .database import Base, SessionLocal, engine
from .routers import admin, auth, bookings, league
from .seed import seed


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    if settings.seed_on_startup:
        with SessionLocal() as db:
            seed(db)
    yield


app = FastAPI(
    title="Football League Booking API",
    description="Browse K League 1 fixtures and standings, and book match tickets.",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(auth.router)
app.include_router(league.router)
app.include_router(bookings.router)
app.include_router(admin.router)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}
