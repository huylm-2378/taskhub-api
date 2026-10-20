FROM python:3.15.0-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY requirements.txt ./
RUN pip install -r requirements.txt \
    && groupadd --gid 10001 taskhub \
    && useradd --uid 10001 --gid taskhub --no-create-home taskhub \
    && mkdir -p /var/lib/taskhub/beat \
    && chown taskhub:taskhub /var/lib/taskhub/beat

COPY . .
USER taskhub
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
