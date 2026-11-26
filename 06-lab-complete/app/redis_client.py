"""
Kết nối Redis dùng chung cho rate limiter và cost guard.

• Client được tạo "lười": redis.from_url không mở kết nối lúc import, nên app vẫn
  khởi động được khi Redis chưa sẵn sàng.
• Timeout ngắn để /ready trả 503 nhanh thay vì treo khi Redis chết.
"""
import redis

from app.config import settings

r = redis.from_url(
    settings.redis_url,
    decode_responses=True,
    socket_connect_timeout=2,
    socket_timeout=2,
    health_check_interval=30,
)


_last_error: str | None = None


def last_error() -> str | None:
    """Lỗi kết nối Redis gần nhất (không chứa mật khẩu) — để log/ready giải thích vì sao 503."""
    return _last_error


def redis_healthy() -> bool:
    global _last_error
    try:
        ok = bool(r.ping())
        _last_error = None
        return ok
    except redis.RedisError as exc:
        _last_error = f"{type(exc).__name__}: {exc}"
        return False
