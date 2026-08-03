FROM python:3.13-slim

WORKDIR /app

# Install dependencies first (better caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/

# Create non-root user
RUN useradd -r appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=10s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:3000/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "3000", "--workers", "2"]