FROM ghcr.io/astral-sh/uv:0.11.0 AS uv
FROM python:3.11-slim
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY hub ./hub
COPY knowledge.json ./knowledge.json
RUN useradd --uid 10001 --create-home hub && mkdir /data && chown hub:hub /data
USER hub
EXPOSE 8095
CMD ["/app/.venv/bin/uvicorn", "hub.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8095", "--workers", "1"]

