FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY services ./services
COPY scripts ./scripts
RUN mkdir -p /app/data/live-cache && chmod -R 777 /app/data
CMD uvicorn services.api.main:app --host 0.0.0.0 --port ${PORT:-7860}
