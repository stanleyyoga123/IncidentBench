FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src

# Kubernetes mounts the component ConfigMap at /app/.env. Local runs use an
# ignored .env copied from .env.example; there is no build-time config folder.

CMD ["python", "src/main.py"]
