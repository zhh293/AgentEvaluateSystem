FROM aquasec/trivy:0.58.1 AS trivy

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 TRIVY_CACHE_DIR=/tmp/trivy-cache
WORKDIR /app
RUN groupadd --gid 10001 app && useradd --uid 10001 --gid app --no-create-home app
COPY --from=trivy /usr/local/bin/trivy /usr/local/bin/trivy
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY --chown=app:app app app
COPY --chown=app:app migrations migrations
COPY --chown=app:app alembic.ini .
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
