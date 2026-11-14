FROM python:3.11.14-slim-bookworm AS dependencies
ENV PIP_NO_CACHE_DIR=1
WORKDIR /build
COPY pyproject.toml README.md requirements.lock ./
COPY src/ ./src/
RUN python -m pip wheel --wheel-dir /wheels -c requirements.lock '.[data,solver,ocr]'

FROM python:3.11.14-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    SBC_ENV=production
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 sbc
COPY --from=dependencies /wheels /wheels
RUN python -m pip install --no-index --find-links=/wheels 'sbc-vision[data,solver,ocr]' \
    && rm -rf /wheels
WORKDIR /app
COPY scripts/prepare_api_demo.py ./scripts/prepare_api_demo.py
COPY data/fixtures/club.synthetic.json data/fixtures/solver.synthetic.json ./data/fixtures/
RUN mkdir -p /app/data/processed && chown -R sbc:sbc /app/data/processed
USER sbc
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"
CMD ["uvicorn", "sbc_vision.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
