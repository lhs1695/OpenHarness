FROM python:3.12-slim

WORKDIR /app

# git is required by the WorktreeManager to create isolated task worktrees.
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

# pip index for this CN environment (override with --build-arg PIP_INDEX_URL=...).
# The default PyPI index is unreliably slow behind the GFW; this also speeds up
# the build-isolation fetch of the hatchling backend.
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ENV PIP_INDEX_URL=$PIP_INDEX_URL

COPY pyproject.toml README.md ./
COPY src ./src
# pyproject.toml force-includes frontend/terminal assets into the wheel.
COPY frontend ./frontend

RUN pip install --no-cache-dir -e ".[service]"

EXPOSE 8000

CMD ["uvicorn", "forgeflow.api.server:app", "--host", "0.0.0.0", "--port", "8000"]
