FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_HOME=/app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
      ca-certificates \
      xvfb \
      libgl1 \
      libglib2.0-0 \
      libxrender1 \
      libxkbcommon0 \
      xauth \
      libdbus-1-3 \
      libgstreamer1.0-0 \
      libgstreamer-plugins-base1.0-0 \
      libnss3 \
      libwebkit2gtk-4.1-0 \
      libxcomposite1 \
      libxdamage1 \
      libxrandr2 \
      libxtst6 \
      libatk-bridge2.0-0 \
      libgtk-3-0 \
      libasound2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR ${APP_HOME}
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

RUN mkdir -p /config /data/uploads /data/jobs /slicer

EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
