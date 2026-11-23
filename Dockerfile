FROM python:3.12-slim

# Kobler imaget på ghcr.io til GitHub-repoet, så CI må opdatere det
LABEL org.opencontainers.image.source="https://github.com/Ljub0129ek/predictive-maintenance-api"
LABEL org.opencontainers.image.description="Predictive Maintenance API (FastAPI + MySQL)"

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY predictive_maintenance ./predictive_maintenance

# Kør ikke som root i containeren
RUN useradd --create-home appuser && mkdir -p /app/logs && chown appuser /app/logs
USER appuser

# Docker tjekker selv, om API'et svarer (bruger /health, som også tjekker databasen)
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"

EXPOSE 8000
CMD ["uvicorn", "predictive_maintenance.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
