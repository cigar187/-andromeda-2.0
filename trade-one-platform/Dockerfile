FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TRADE_ONE_CONFIG=/app/config/trade-one.json

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY config ./config
COPY plugins ./plugins
RUN pip install --no-cache-dir ".[api]"

EXPOSE 8080
CMD ["uvicorn", "trade_one.api:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080"]

