# rusa — AI Voiceover for Movies
# Build: docker build -t bortoq/rusa .
# Run:   docker run --rm -v $(pwd):/data bortoq/rusa movie.mkv

FROM python:3.11-slim

# Install system deps: ffmpeg for audio/video processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy everything and install
COPY . .
RUN pip install --no-cache-dir .[webui] && \
    pip install --no-cache-dir edge-tts tqdm langdetect

# Volume for input/output files
VOLUME /data
WORKDIR /data

ENTRYPOINT ["rusa"]
CMD ["--help"]
