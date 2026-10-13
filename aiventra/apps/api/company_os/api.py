from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .observability import configure_logging, request_trace
from .routes import (
    administration,
    agent_operations,
    business,
    case_operations,
    checkout_operations,
    client_operations,
    closure_operations,
    consultation,
    conversations,
    crypto_operations,
    delivery_operations,
    deployment_operations,
    engineering,
    history_operations,
    identity,
    memory_operations,
    package_operations,
    project_setup_operations,
    provider_operations,
    publication_operations,
    quality_operations,
    readiness_operations,
    refinement_operations,
    release_operations,
    spending_operations,
    staffing_operations,
)


@asynccontextmanager
async def lifespan(_app):
    settings().validate_startup()
    yield


configure_logging()
app = FastAPI(title="Aiventra OS", version="0.2.0", lifespan=lifespan)
app.middleware("http")(request_trace)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings().web_origin],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    expose_headers=["X-Request-ID"],
)
for router in (
    identity.router,
    history_operations.router,
    project_setup_operations.router,
    consultation.router,
    administration.router,
    engineering.router,
    business.router,
    conversations.router,
    provider_operations.router,
    agent_operations.router,
    memory_operations.router,
    staffing_operations.router,
    spending_operations.router,
    publication_operations.router,
    delivery_operations.router,
    package_operations.router,
    release_operations.router,
    client_operations.router,
    case_operations.router,
    closure_operations.router,
    checkout_operations.router,
    readiness_operations.router,
    refinement_operations.router,
    quality_operations.router,
    deployment_operations.router,
    crypto_operations.router,
):
    app.include_router(router)
