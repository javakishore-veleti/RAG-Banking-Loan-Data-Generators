FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src/ ./src/
# F016: seed terminology for the generator (loaded at runtime; the
# generator falls back to built-in terms if this is absent).
COPY data/seeds/ ./data/seeds/
ENV PYTHONPATH=/app/src
# Batch job entrypoint: the worker polls SQS until the queue is empty.
CMD ["python3", "src/worker/batch_worker.py"]
