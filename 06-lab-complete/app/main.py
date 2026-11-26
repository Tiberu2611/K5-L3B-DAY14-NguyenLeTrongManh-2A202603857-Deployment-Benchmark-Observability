"""
Production AI Agent — Part 6 Final Project

    uvicorn app.main:app --workers 2
    python check_production_ready.py
"""
import json
import logging
import signal
import sys
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import redis
from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.auth import verify_api_key
from app.config import redact_url, settings
from app.cost_guard import check_budget, estimate_tokens, record_cost
from app.rate_limiter import check_rate_limit
from app.redis_client import last_error, r, redis_healthy
from utils.mock_llm import ask as llm_ask


# ─────────────────────────────────────────────────────────
# Structured logging — mỗi dòng log là 1 JSON object
# ─────────────────────────────────────────────────────────
class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "lvl": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        entry.update(getattr(record, "fields", {}))
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)  # json.dumps escape \n → vẫn 1 dòng
        return json.dumps(entry, ensure_ascii=False, default=str)


def _setup_logging() -> logging.Logger:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(settings.log_level)
    return logging.getLogger("agent")


logger = _setup_logging()


def log(event: str, level: int = logging.INFO, **fields) -> None:
    logger.log(level, event, extra={"fields": fields})


# ─────────────────────────────────────────────────────────
# Graceful shutdown
# ─────────────────────────────────────────────────────────
_state = {"shutting_down": False}


def _install_sigterm_hook() -> None:
    """Đánh dấu đang tắt (để /ready trả 503) rồi gọi lại handler cũ của uvicorn.

    uvicorn tự lo phần chính: ngừng nhận kết nối mới, chờ request đang chạy xong,
    chạy lifespan shutdown rồi thoát với exit code 0.
    """
    previous = signal.getsignal(signal.SIGTERM)

    def handler(signum, frame):
        _state["shutting_down"] = True
        log("graceful_shutdown_started", signal="SIGTERM", draining=True)
        if callable(previous):
            previous(signum, frame)

    try:
        signal.signal(signal.SIGTERM, handler)
    except ValueError:  # không ở main thread (vd test client) → bỏ qua
        pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    _install_sigterm_hook()
    if not settings.agent_api_key:
        log("agent_api_key_missing", logging.WARNING, note="all /ask requests will be rejected")
    redis_target = redact_url(settings.redis_url)
    if "localhost" in redis_target or "127.0.0.1" in redis_target:
        if settings.environment == "production":
            log("redis_url_points_to_localhost", logging.WARNING, redis=redis_target,
                hint="set REDIS_URL on the agent service to your cloud Redis connection string")
    if redis_healthy():
        log("redis_connected", redis=redis_target)
    else:
        log("redis_unreachable", logging.ERROR, redis=redis_target, error=last_error())
    log("startup", environment=settings.environment,
        rate_limit_per_minute=settings.rate_limit_per_minute,
        daily_budget_usd=settings.daily_budget_usd,
        monthly_budget_usd=settings.monthly_budget_usd)
    yield
    # Tới đây uvicorn đã xử lý xong mọi request đang chạy
    _state["shutting_down"] = True
    try:
        r.close()
    except Exception:
        pass
    log("graceful_shutdown_complete")


app = FastAPI(title="Production AI Agent", lifespan=lifespan)


# ─────────────────────────────────────────────────────────
# Middleware log request + xử lý lỗi (không lộ stack trace)
# ─────────────────────────────────────────────────────────
@app.middleware("http")
async def access_log(request: Request, call_next):
    started = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        log("request", method=request.method, path=request.url.path, status=status,
            ms=round((time.perf_counter() - started) * 1000, 1))


@app.exception_handler(redis.RedisError)
async def redis_error_handler(request: Request, exc: redis.RedisError):
    log("redis_unavailable", logging.ERROR, path=request.url.path,
        redis=redact_url(settings.redis_url), error=f"{type(exc).__name__}: {exc}")
    return JSONResponse(status_code=503, content={"detail": "Service temporarily unavailable"},
                        headers={"Retry-After": "5"})


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    logger.error("unhandled_error", exc_info=exc, extra={"fields": {"path": request.url.path}})
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


# ─────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────
class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    user_id: str | None = Field(default=None, max_length=128)


@app.get("/health")
def health():
    """Liveness: process còn sống là 200 — không phụ thuộc Redis."""
    return {"status": "ok"}


@app.get("/ready")
def ready():
    """Readiness: chỉ nhận traffic khi Redis kết nối được và chưa bắt đầu tắt."""
    if _state["shutting_down"]:
        return JSONResponse(status_code=503, content={"status": "shutting_down"})
    if not redis_healthy():
        # Log chi tiết (host đã che mật khẩu) để biết vì sao 503; response không lộ thông tin nội bộ
        log("ready_failed", logging.WARNING, redis=redact_url(settings.redis_url), error=last_error())
        return JSONResponse(status_code=503, content={"status": "not_ready", "redis": "down"})
    return {"status": "ready", "redis": "ok"}


@app.get("/ask", include_in_schema=False)
def ask_wrong_method(api_key: str = Depends(verify_api_key)):
    """Xác thực trước khi báo sai method: GET không có key → 401, không lộ endpoint."""
    return JSONResponse(status_code=405, content={"detail": "Use POST /ask"},
                        headers={"Allow": "POST"})


@app.post("/ask")
def ask(body: AskRequest, api_key: str = Depends(verify_api_key)):
    check_rate_limit(api_key)                     # 429
    check_budget()                                # 402
    answer = llm_ask(body.question)
    cost = record_cost(estimate_tokens(body.question), estimate_tokens(answer))
    log("ask", user_id=body.user_id, q_chars=len(body.question), cost_usd=round(cost, 8))
    return {"question": body.question, "answer": answer}
