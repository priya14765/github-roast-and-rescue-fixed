# Small image for Google Cloud Run. Secrets are NOT baked in: they arrive as environment variables.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Run as an unprivileged user.
RUN useradd --create-home appuser
USER appuser

# One worker keeps the in-memory cache shared across requests; threads handle concurrency.
CMD exec gunicorn --bind "0.0.0.0:${PORT}" --workers 1 --threads 8 --timeout 60 "app.main:create_app()"
