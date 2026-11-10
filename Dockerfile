# docker compose up 으로 실행하세요 (README 참고).
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PX_DATA_DIR=/data

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY problem_extractor ./problem_extractor
RUN pip install --no-cache-dir . && useradd --create-home --uid 1000 app && mkdir -p /data && chown app /data

USER app
VOLUME ["/data"]
EXPOSE 8000
CMD ["uvicorn", "problem_extractor.main:app", "--host", "0.0.0.0", "--port", "8000"]
