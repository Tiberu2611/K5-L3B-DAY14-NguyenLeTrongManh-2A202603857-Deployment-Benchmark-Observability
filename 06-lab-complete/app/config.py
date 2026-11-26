"""
Config — 12-Factor: mọi cấu hình đọc từ biến môi trường.

Giá trị mặc định chỉ dành cho chạy local. Secret (AGENT_API_KEY) KHÔNG có giá trị
mặc định: để trống thì mọi request /ask đều bị từ chối (401), không bao giờ "mở toang".
"""
import os
from urllib.parse import quote, urlsplit, urlunsplit
from dataclasses import dataclass, field

from dotenv import load_dotenv

# Đọc .env nếu có (chỉ tiện cho local). Biến môi trường thật luôn được ưu tiên.
load_dotenv(override=False)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


def _resolve_redis_url() -> str:
    """Tìm URL Redis theo thứ tự ưu tiên.

    Lỗi deploy hay gặp nhất: service agent không có REDIS_URL (biến chỉ nằm ở service
    Redis, hoặc nền tảng đặt tên khác) → app rơi về localhost → /ready và /ask trả 503.
    Ngoài REDIS_URL, nhận thêm các tên biến Railway/Render/Upstash hay cấp.
    """
    for name in ("REDIS_URL", "REDIS_PRIVATE_URL", "REDIS_PUBLIC_URL", "KV_URL", "UPSTASH_REDIS_URL"):
        value = os.getenv(name, "").strip()
        if value:
            return value
    host = os.getenv("REDISHOST") or os.getenv("REDIS_HOST")
    if host:
        port = os.getenv("REDISPORT") or os.getenv("REDIS_PORT") or "6379"
        user = os.getenv("REDISUSER") or os.getenv("REDIS_USER") or ""
        password = os.getenv("REDISPASSWORD") or os.getenv("REDIS_PASSWORD") or ""
        auth = f"{quote(user, safe='')}:{quote(password, safe='')}@" if password else ""
        return f"redis://{auth}{host}:{port}/0"
    return "redis://localhost:6379/0"


def redact_url(url: str) -> str:
    """Bỏ mật khẩu khỏi URL trước khi ghi log."""
    parts = urlsplit(url)
    if parts.password:
        netloc = f"{parts.username or ''}:***@{parts.hostname}" + (f":{parts.port}" if parts.port else "")
        parts = parts._replace(netloc=netloc)
    return urlunsplit(parts)


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    port: int = field(default_factory=lambda: _env_int("PORT", 8000))
    environment: str = field(default_factory=lambda: os.getenv("ENVIRONMENT", "development"))
    agent_api_key: str = field(default_factory=lambda: os.getenv("AGENT_API_KEY", ""))
    redis_url: str = field(default_factory=_resolve_redis_url)
    rate_limit_per_minute: int = field(default_factory=lambda: _env_int("RATE_LIMIT_PER_MINUTE", 10))
    daily_budget_usd: float = field(default_factory=lambda: _env_float("DAILY_BUDGET_USD", 1.0))
    monthly_budget_usd: float = field(default_factory=lambda: _env_float("MONTHLY_BUDGET_USD", 10.0))
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO").upper())


settings = Settings()
