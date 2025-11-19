FROM python:3.11-slim

WORKDIR /app

# Install ffmpeg
RUN apt-get update && \
    apt-get install -y ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Run the bot
CMD ["gunicorn", "--bind", "0.0.0.0:$PORT", "bot:app"]