# rusa — AI Voiceover for Movies
# Build: docker build -t rusa:test .
# Run:   docker run --rm -v $(pwd):/data rusa:test movie.mkv

FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .
RUN pip install --no-cache-dir .

ENTRYPOINT ["rusa"]
CMD ["--help"]
