# loop-cr-review — homelab web front-end
# Build:  docker build -t loop-cr-review .
# Run:    docker run --rm -p 8000:8000 loop-cr-review
FROM python:3.14-slim

WORKDIR /app

# System libs matplotlib needs at runtime (Agg backend, font rendering)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libfreetype6 libpng16-16 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-web.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-web.txt

COPY . .

EXPOSE 8000
# 2 sync workers: each handles one request at a time, so the module-level
# slot globals in generate_report() stay safe per worker.
CMD ["gunicorn", "-b", "0.0.0.0:8000", "-w", "2", "--timeout", "120", "webapp:app"]
