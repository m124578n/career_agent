# 本機爬蟲 agent。容器出口走主機網路 → 一樣是住宅 IP，104 不會擋。
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

# 先裝相依（吃 layer cache，原始碼改動不必重裝）
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# 放原始碼
COPY agent.py ./

# 用 build 階段裝好的環境直接跑，啟動不連 PyPI
CMD ["uv", "run", "--no-dev", "--no-sync", "python", "-u", "agent.py"]
