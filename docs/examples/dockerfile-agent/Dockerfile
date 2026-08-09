FROM python:3.12-slim

WORKDIR /app
COPY --chown=65532:65532 . /app

USER 65532:65532
CMD ["python", "/app/main.py"]
