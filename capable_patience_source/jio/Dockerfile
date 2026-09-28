FROM mcr.microsoft.com/playwright/python:v1.52.0-jammy

WORKDIR /app
ENV PYTHONUNBUFFERED=1
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 9090
CMD ["python3", "main.py"]
