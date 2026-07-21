FROM python:3.11-slim

# Install system dependencies including ffmpeg and nodejs (for yt-dlp JS decryption)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirement files and install python dependencies
COPY requirements.txt .
ENV PIP_ROOT_USER_ACTION=ignore
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir -U yt-dlp

# Copy source code
COPY . .

# Run the bot
CMD ["python", "main.py"]
