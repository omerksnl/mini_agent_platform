FROM python:3.12-slim

ARG VISUAL_TENSORFLOW_PACKAGE=tensorflow-cpu==2.20.0

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN grep -v '^tensorflow-cpu==' requirements.txt > requirements-runtime.txt \
    && pip install --no-cache-dir -r requirements-runtime.txt \
    && pip install --no-cache-dir "${VISUAL_TENSORFLOW_PACKAGE}"

COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app
COPY docker-entrypoint.sh ./docker-entrypoint.sh
RUN chmod +x ./docker-entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["./docker-entrypoint.sh"]
