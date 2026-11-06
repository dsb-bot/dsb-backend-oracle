from contextlib import asynccontextmanager
from datetime import date
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from dsb_bot.config import Settings
from dsb_bot.repository import ScheduleRepository


def create_app(
    settings: Settings | None = None,
    repository: ScheduleRepository | None = None,
) -> FastAPI:
    config = settings or Settings.from_env()
    schedule_repository = repository or ScheduleRepository(config.database_path)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        schedule_repository.initialize()
        app.state.repository = schedule_repository
        yield

    app = FastAPI(title="DSB Schedule API", version="1.0.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[config.frontend_origin],
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    @app.get("/healthz")
    def health(request: Request) -> dict[str, str]:
        request.app.state.repository.count()
        return {"status": "ok"}

    @app.get("/api/v1/plans")
    def list_plans(
        request: Request,
        start_date: Annotated[date | None, Query(alias="from")] = None,
        end_date: Annotated[date | None, Query(alias="to")] = None,
    ) -> dict[str, list[dict[str, str]]]:
        if start_date is not None and end_date is not None and start_date > end_date:
            raise HTTPException(status_code=422, detail="'from' must not be after 'to'")
        plans = request.app.state.repository.list_plans(start_date, end_date)
        return {
            "plans": [
                {
                    "date": plan.date.isoformat(),
                    "title": plan.title,
                    "updated_at": plan.updated_at.isoformat(),
                    "html_url": f"/api/v1/plans/{plan.date.isoformat()}/html",
                }
                for plan in plans
            ]
        }

    @app.get("/api/v1/plans/{plan_date}")
    def get_plan_metadata(plan_date: date, request: Request) -> dict[str, str]:
        plan = request.app.state.repository.get(plan_date)
        if plan is None:
            raise HTTPException(status_code=404, detail="Schedule not found")
        return {
            "date": plan.date.isoformat(),
            "title": plan.title,
            "updated_at": plan.updated_at.isoformat(),
            "html_url": f"/api/v1/plans/{plan.date.isoformat()}/html",
        }

    @app.get("/api/v1/plans/{plan_date}/html")
    def get_plan_html(plan_date: date, request: Request) -> Response:
        plan = request.app.state.repository.get(plan_date)
        if plan is None:
            raise HTTPException(status_code=404, detail="Schedule not found")
        return Response(
            content=plan.html_content,
            media_type=plan.content_type,
            headers={
                "ETag": f'"{plan.content_hash}"',
                "Cache-Control": "public, max-age=60",
                "X-Content-Type-Options": "nosniff",
            },
        )

    @app.get("/api/v1/sync-status")
    def sync_status(request: Request) -> dict[str, str | None]:
        return {
            "last_successful_sync": request.app.state.repository.last_successful_sync()
        }

    return app


app = create_app()
