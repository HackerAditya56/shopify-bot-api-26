FROM mcr.microsoft.com/playwright/python:v1.52.0-jammy

WORKDIR /app
ENV PYTHONUNBUFFERED=1
ENV PROXIES_FILE=/app/proxies.txt
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
CMD ["sh", "-c", "uvicorn api:app --host 0.0.0.0 --port ${PORT:-8000}"]
