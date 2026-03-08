FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir yt-dlp flask gunicorn

WORKDIR /app
COPY server.py .

EXPOSE 8080
CMD ["gunicorn", "-b", "0.0.0.0:8080", "-w", "4", "--timeout", "120", "server:app"]
