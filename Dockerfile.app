# syntax=docker/dockerfile:1

FROM python:3.11-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential tzdata poppler-utils tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

# ---------- DEV ----------
FROM base AS dev
COPY requirements.txt /app/requirements.txt
RUN python -m pip install --upgrade pip \
 && pip install --no-cache-dir -r /app/requirements.txt \
 && pip install --no-cache-dir watchfiles
WORKDIR /app
CMD ["python","-m","watchfiles","--filter","python","--ignore-paths","data,logs","--","python","-m","LuckyBot.main"]

# ---------- PROD ----------
FROM base AS prod
COPY requirements.txt /app/requirements.txt
RUN python -m pip install --upgrade pip \
 && pip install --no-cache-dir -r /app/requirements.txt
COPY . /app
CMD ["python","-m","LuckyBot.main"]
