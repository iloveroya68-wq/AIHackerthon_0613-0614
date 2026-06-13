FROM python:3.11-slim

ARG INSTALL_DEV=false

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev libgomp1 gcc g++ && rm -rf /var/lib/apt/lists/*

RUN pip install uv

WORKDIR /app
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy contracts first so uv can resolve the path dependency
COPY contracts/ /contracts/
COPY engine/ /engine/
COPY backend/pyproject.toml backend/uv.lock* ./

RUN if [ "$INSTALL_DEV" = "true" ]; then \
      uv sync --extra dev; \
    else \
      uv sync --no-dev; \
    fi

COPY backend/ .

EXPOSE 8000

CMD ["sh", "-c", "python manage.py migrate && exec gunicorn drift_backend.wsgi:application --bind 0.0.0.0:8000 --workers 2 --timeout 180"]
