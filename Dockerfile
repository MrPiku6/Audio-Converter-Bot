# Debian-based Python image ka istemal karein jisme apt-get ho
FROM python:3.9-slim

# Working directory set karein
WORKDIR /app

# System dependencies (ffmpeg aur portaudio) install karein
RUN apt-get update && apt-get install -y ffmpeg portaudio19-dev

# requirements.txt file ko copy karein
COPY requirements.txt .

# Python packages install karein
RUN pip install --no-cache-dir -r requirements.txt

# Baaki sabhi project files ko copy karein
COPY . .

# Bot ko start karne ke liye default command
CMD ["python", "bot.py"]