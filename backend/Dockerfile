FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app

ENV PATH="/app/.venv/bin:$PATH"

# Build revision stamped into the image; exposed by GET /api/health so the
# blue-green deploy can verify which code is actually serving traffic.
ARG GIT_SHA=unknown
ENV APP_REVISION=${GIT_SHA}

EXPOSE 8000

# --workers 1 is deliberate, not an oversight: ConnectionManager keeps chat
# rooms in this process's memory, so a second worker would own half of the
# sockets and only reach that half when broadcasting. Raise it only together
# with a shared broker (Redis pub/sub).
#
# The WS ping keeps half-open sockets (browser gone, proxy silently dropping the
# upstream side) from lingering: uvicorn closes them after --ws-ping-timeout,
# and the frontend watchdog expects a pong at least every 25s.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--ws-ping-interval", "20", "--ws-ping-timeout", "20", "--timeout-keep-alive", "75"]
