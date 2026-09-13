# Simple, single-process image. SQLite lives on disk inside the container --
# mount /app/storage as a volume (see docker-compose.yml / README) so your
# data and generated documents survive restarts and redeploys.
FROM python:3.12-slim

WORKDIR /app

# System deps for python-docx/pypdf are pure-python, so no extra system
# packages are needed beyond build essentials for a couple of C-extension deps.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p storage/documents storage/uploads

EXPOSE 8000

# Respects $PORT if the platform sets one (Render/Railway do); falls back to 8000.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
