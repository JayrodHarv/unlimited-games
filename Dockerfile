FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATABASE_PATH=/app/data/games.db

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --no-create-home app \
    && mkdir -p /app/data \
    && chown app:app /app/data

COPY --chown=app:app backend ./backend
COPY --chown=app:app frontend ./frontend
USER app
EXPOSE 8000

CMD ["gunicorn", "--chdir", "backend", "--bind", "0.0.0.0:8000", "--workers", "1", "--threads", "4", "--access-logfile", "-", "--error-logfile", "-", "app:create_app()"]
