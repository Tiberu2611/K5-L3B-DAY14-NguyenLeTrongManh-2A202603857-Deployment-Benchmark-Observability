"""
API Key authentication (tiêu chí 6).

• Client gửi header  X-API-Key: <key>
• Key phải trùng biến môi trường AGENT_API_KEY
• Thiếu hoặc sai key → HTTP 401
"""
import hmac

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

from app.config import settings

# auto_error=False: tự trả 401 thay vì 403 mặc định của FastAPI khi thiếu header
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(api_key: str | None = Security(api_key_header)) -> str:
    """Dependency cho /ask. Trả về API key hợp lệ (dùng làm khoá rate limit)."""
    expected = settings.agent_api_key
    # Không cấu hình key → từ chối tất cả, không bao giờ cho qua mặc định.
    # compare_digest: so sánh thời gian hằng, tránh timing attack.
    if not api_key or not expected or not hmac.compare_digest(api_key, expected):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    return api_key
