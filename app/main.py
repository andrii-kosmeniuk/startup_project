from fastapi import FastAPI

from app.customers.router import router as customers_router
from app.properties.router import router as properties_router
from app.tickets.router import router as tickets_router

app = FastAPI(
    title="Fonio FDE Lab",
    description="Mock integration API for HausPilot Immobilienverwaltung GmbH.",
    version="0.1.0",
)

app.include_router(customers_router)
app.include_router(properties_router)
app.include_router(tickets_router)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}
