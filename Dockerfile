FROM python:3.13-slim

WORKDIR /app
ENV PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl build-essential \
 && rm -rf /var/lib/apt/lists/*

# Install Python deps first for better layer caching
COPY requirements.txt ./
RUN pip install -r requirements.txt

# Copy the whole project to /app/
COPY . /app/

# TO DO: non-root user

# Expose FastAPI port
EXPOSE 8001

# Default command can be overridden by docker-compose/k8s
CMD ["uvicorn", "main_app:app", "--host", "0.0.0.0", "--port", "8001"]

# Labels for Docker Hub
LABEL org.opencontainers.image.title="Metasync"
LABEL org.opencontainers.image.description="Async LLM orchestration pipeline with job queue, multi-provider support, and metaprompting optimization."
LABEL org.opencontainers.image.url="https://github.com/peakedev/metasync"
LABEL org.opencontainers.image.source="https://github.com/peakedev/metasync"