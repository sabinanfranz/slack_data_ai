from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv(filename=".env", usecwd=True), override=False)

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.db import check_db, init_db
from app.routers.api_channels import router as api_channels_router
from app.routers.api_ingest import router as api_ingest_router
from app.routers.api_thread_reports import router as api_thread_reports_router
from app.routers.api_stats import router as api_stats_router
from app.routers.api_threads import router as api_threads_router
from app.routers.pages import router as pages_router


def create_app() -> FastAPI:
    app = FastAPI(title="Slack Digest Admin")

    # Static
    app.mount("/static", StaticFiles(directory="app/static"), name="static")

    # Routes
    app.include_router(pages_router)
    app.include_router(api_channels_router)
    app.include_router(api_threads_router)
    app.include_router(api_stats_router)
    app.include_router(api_thread_reports_router)
    app.include_router(api_ingest_router)

    @app.on_event("startup")
    def _startup():
        init_db()

    @app.get("/", include_in_schema=False)
    def root():
        return RedirectResponse(url="/channels")

    @app.get("/healthz")
    def healthz():
        return {"ok": True, "db": check_db()}

    return app


app = create_app()
