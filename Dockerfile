FROM node:22-slim AS web-builder

WORKDIR /app

COPY src/website/package*.json ./src/website/
RUN cd src/website && npm ci

COPY src/website ./src/website
RUN cd src/website && npm run build


FROM python:3.13-slim

ARG APP_VERSION=dev
ARG BUILD_SHA=unknown

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src
ENV STQB_DATA_DIR=/app/data
ENV STQB_APP_VERSION=${APP_VERSION}
ENV STQB_BUILD_SHA=${BUILD_SHA}

LABEL org.opencontainers.image.source="https://github.com/MelodyKnit/SmartAnswer"
LABEL org.opencontainers.image.version="${APP_VERSION}"
LABEL org.opencontainers.image.revision="${BUILD_SHA}"

WORKDIR /app

RUN sed -i 's|http://deb.debian.org/debian|https://mirrors.tuna.tsinghua.edu.cn/debian|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update \
    && apt-get install -y --no-install-recommends chromium ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /app/data/runtime /app/data/logs /app/data/normalized /app/configs

RUN pip install --no-cache-dir --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple \
    && pip install --no-cache-dir \
        -i https://pypi.tuna.tsinghua.edu.cn/simple \
        dulwich \
        fastapi \
        httpx \
        jinja2 \
        pillow \
        playwright \
        psycopg[binary] \
        python-dotenv \
        python-multipart \
        rapidocr-onnxruntime \
        rapidfuzz \
        redis \
        sqlalchemy \
        uvicorn

COPY configs ./configs
COPY client-scripts ./client-scripts
COPY scripts ./scripts
COPY src ./src
COPY --from=web-builder /app/src/study_qb_assistant/api/static ./src/study_qb_assistant/api/static
COPY README.md pyproject.toml ./

EXPOSE 8765

CMD ["uvicorn", "study_qb_assistant.runtime:create_runtime_app", "--factory", "--host", "0.0.0.0", "--port", "8765", "--app-dir", "src"]
