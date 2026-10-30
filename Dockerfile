FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    SBC_ENV=production

WORKDIR /app
COPY pyproject.toml README.md requirements.lock ./
COPY src/ ./src/
RUN python -m pip install -c requirements.lock . && useradd --create-home --uid 10001 sbc
USER sbc

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"
CMD ["uvicorn", "sbc_vision.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
