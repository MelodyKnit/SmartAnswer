FROM node:22-slim AS web-builder

WORKDIR /app

COPY src/website/package*.json ./src/website/
RUN cd src/website && npm ci

COPY src/website ./src/website
RUN cd src/website && npm run build


FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src
ENV STQB_DATA_DIR=/app/data

WORKDIR /app

RUN mkdir -p /app/data/runtime /app/data/logs /app/data/normalized /app/configs

RUN pip install --no-cache-dir --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple \
    && pip install --no-cache-dir \
        -i https://pypi.tuna.tsinghua.edu.cn/simple \
        dulwich \
        fastapi \
        httpx \
        playwright \
        psycopg[binary] \
        python-dotenv \
        rapidocr-onnxruntime \
        rapidfuzz \
        redis \
        sqlalchemy \
        uvicorn

COPY configs ./configs
COPY scripts ./scripts
COPY src ./src
COPY --from=web-builder /app/src/study_qb_assistant/api/static ./src/study_qb_assistant/api/static
COPY README.md pyproject.toml ./

EXPOSE 8765

CMD ["uvicorn", "study_qb_assistant.runtime:create_runtime_app", "--factory", "--host", "0.0.0.0", "--port", "8765", "--app-dir", "src"]
