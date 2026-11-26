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


def redis_healthy() -> bool:
    try:
        return bool(r.ping())
    except redis.RedisError:
        return False
