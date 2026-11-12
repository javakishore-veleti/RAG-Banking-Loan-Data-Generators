FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src/ ./src/
COPY config/ ./config/
ENV PYTHONPATH=/app/src
# Batch job entrypoint: the worker polls SQS until the queue is empty.
CMD ["python3", "src/indexer/worker.py"]
