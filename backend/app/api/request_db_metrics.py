from __future__ import annotations

from time import perf_counter

from fastapi import Request, Response
from sqlalchemy.ext.asyncio import AsyncSession


def get_request_db_metrics(request: Request) -> dict[str, float]:
    metrics = getattr(request.state, "db_metrics", None)
    if metrics is None:
        metrics = {"query_count": 0.0, "query_duration_ms": 0.0}
        request.state.db_metrics = metrics
    return metrics


def instrument_session_for_request(request: Request, session: AsyncSession) -> None:
    metrics = get_request_db_metrics(request)
    original_execute = session.execute

    async def instrumented_execute(*args, **kwargs):
        start = perf_counter()
        try:
            return await original_execute(*args, **kwargs)
        finally:
            metrics["query_count"] += 1
            metrics["query_duration_ms"] += (perf_counter() - start) * 1000

    session.execute = instrumented_execute
    session.info["request_db_metrics_original_execute"] = original_execute


def restore_session_after_request(session: AsyncSession) -> None:
    original_execute = session.info.pop("request_db_metrics_original_execute", None)
    if original_execute is not None:
        session.execute = original_execute


def finalize_request_db_metrics(
    response: Response,
    request: Request,
    *,
    header_prefix: str,
    request_start: float,
) -> dict[str, float]:
    metrics = get_request_db_metrics(request)
    query_count = int(metrics["query_count"])
    query_duration_ms = round(metrics["query_duration_ms"], 2)
    request_duration_ms = round((perf_counter() - request_start) * 1000, 2)

    response.headers[f"{header_prefix}-Query-Count"] = str(query_count)
    response.headers[f"{header_prefix}-Query-Time-Ms"] = f"{query_duration_ms:.2f}"
    response.headers[f"{header_prefix}-Request-Time-Ms"] = f"{request_duration_ms:.2f}"

    return {
        "query_count": query_count,
        "query_duration_ms": query_duration_ms,
        "request_duration_ms": request_duration_ms,
    }
