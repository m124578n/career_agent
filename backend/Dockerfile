# 104 Job Tracker 後端（FastAPI）。build context = backend/
FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

# 先裝相依（吃 layer cache，原始碼改動不必重裝）
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-install-project --no-dev

# 再放原始碼並安裝專案本身
COPY src ./src
RUN uv sync --frozen --no-dev

EXPOSE 8000

# Zeabur 等平台會帶 PORT；exec 取代 shell 以正確接收 SIGTERM
CMD ["sh", "-c", "exec uv run uvicorn job_tracker.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
