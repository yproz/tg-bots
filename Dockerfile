FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN apt-get update \
 && apt-get install -y --no-install-recommends gcc build-essential \
 && pip install -r requirements.txt \
 && apt-get purge -y --auto-remove gcc build-essential \
 && rm -rf /var/lib/apt/lists/*

COPY . .

CMD ["python", "-m", "bot.main"]