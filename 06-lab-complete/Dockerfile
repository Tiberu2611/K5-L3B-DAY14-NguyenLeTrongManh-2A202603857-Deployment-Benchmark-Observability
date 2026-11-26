# ============================================================
# Production Dockerfile — multi-stage
#   Stage 1 (builder): cài dependencies vào virtualenv /opt/venv
#   Stage 2 (runtime): chỉ copy venv + source, chạy bằng user non-root
# ============================================================

# ---------- Stage 1: builder ----------
FROM python:3.12-slim as builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# requirements trước, source sau → đổi code không phải cài lại dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt


# ---------- Stage 2: runtime ----------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    PORT=8000 \
    ENVIRONMENT=production

RUN groupadd --system app && useradd --system --gid app --no-create-home app

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY --chown=app:app app/ ./app/
COPY --chown=app:app utils/ ./utils/

USER app

EXPOSE 8000

# Image slim không có curl → dùng Python để gọi /health
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8000\")}/health', timeout=3)" || exit 1

# exec → uvicorn là PID 1, nhận SIGTERM trực tiếp khi `docker stop`.
# --timeout-graceful-shutdown giữ thời gian tắt < 10s của docker stop.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers ${WEB_CONCURRENCY:-2} --timeout-graceful-shutdown 8"]
