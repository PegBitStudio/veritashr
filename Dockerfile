# VeritasHR - runs fully offline inside a private network. No outbound calls are made at runtime.
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    VERITAS_DATA_DIR=/data VERITAS_AUDIT_LOG=/audit/decisions.jsonl \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
COPY ui ./ui
COPY scripts ./scripts
COPY data/raw /data

# Non-root user; source data mounted read-only, audit log on its own volume
RUN useradd --create-home veritas && mkdir -p /audit && chown veritas /audit
USER veritas
VOLUME ["/data", "/audit"]
EXPOSE 8501

CMD ["streamlit", "run", "ui/app.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true"]
