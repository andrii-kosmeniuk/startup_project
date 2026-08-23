from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.customers.router import router as customers_router
from app.properties.router import router as properties_router
from app.tickets.router import router as tickets_router
from app.calls.router import router as calls_router
from app.data.database import Base, SessionLocal, engine
from app.data.seed import seed_database
from app.security.api_key import validate_api_key_configuration
from app.observability.middleware import RequestObservabilityMiddleware


@asynccontextmanager
async def lifespan(_: FastAPI):
    validate_api_key_configuration()
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as session:
        seed_database(session)
    yield

app = FastAPI(
    title="Fonio FDE Lab",
    description="Mock integration API for HausPilot Immobilienverwaltung GmbH.",
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(RequestObservabilityMiddleware)

app.include_router(customers_router)
app.include_router(properties_router)
app.include_router(tickets_router)
app.include_router(calls_router)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}
