# Slim version for smaller size
FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Install FFmpeg and system dependencies
RUN apt-get update && \
    apt-get install -y ffmpeg gcc && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy code
COPY . .

# Port variable set karein (Render automatically inject karta hai, par default set karna achha hai)
ENV PORT=8080

# Command to run the bot
CMD ["python", "bot.py"]