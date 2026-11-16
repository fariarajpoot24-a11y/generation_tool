FROM mcr.microsoft.com/playwright/python:v1.47.0-jammy
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV HEADLESS=true PYTHONUNBUFFERED=1
CMD gunicorn app:app --workers 1 --threads 4 --timeout 300 --bind 0.0.0.0:${PORT:-10000}