FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies including ffmpeg, Khmer fonts, build-essential for C++ compilation, and Node.js 20 LTS
RUN apt-get update -qq && apt-get install -y -qq --no-install-recommends \
    curl gnupg build-essential cmake git libgomp1 \
    fonts-khmeros fonts-khmeros-core fonts-noto-extra && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y -qq --no-install-recommends ffmpeg nodejs && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirement files and install python dependencies
COPY requirements.txt .
ENV PIP_ROOT_USER_ACTION=ignore
ENV MAX_JOBS=2
ENV CMAKE_BUILD_PARALLEL_LEVEL=2

RUN pip install --no-cache-dir llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/wheels/cpu || pip install --no-cache-dir llama-cpp-python
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir -U yt-dlp

# Copy source code
COPY . .

# Run the bot
CMD ["python", "main.py"]
