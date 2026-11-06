FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml README.md ./
COPY dsb_bot ./dsb_bot
RUN python -m pip install --no-cache-dir . \
    && mkdir -p /data \
    && useradd --system --uid 10001 --create-home appuser \
    && chown appuser:appuser /data

USER appuser
EXPOSE 8000
CMD ["uvicorn", "dsb_bot.api:app", "--host", "0.0.0.0", "--port", "8000"]
