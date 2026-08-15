# loop-cr-review — homelab web front-end
# Build:  docker build -t loop-cr-review .
# Run:    docker run --rm -p 8000:8000 loop-cr-review
# The version shown in the report/web is baked from `git describe` at build time.

# ---- version stage: resolve the version from git (falls back to "dev") -------
FROM python:3.14-slim AS version
WORKDIR /src
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
COPY . .
RUN echo "VERSION = \"$(git describe --tags --dirty --always 2>/dev/null || echo dev)\"" > _version.py

# ---- runtime -----------------------------------------------------------------
FROM python:3.14-slim
WORKDIR /app

# System libs matplotlib needs at runtime (Agg backend, font rendering)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libfreetype6 libpng16-16 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-web.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-web.txt

COPY . .
COPY --from=version /src/_version.py _version.py
RUN rm -rf .git

EXPOSE 8000
# 2 sync workers: each handles one request at a time, so the module-level
# slot globals in generate_report() stay safe per worker.
CMD ["gunicorn", "-b", "0.0.0.0:8000", "-w", "2", "--timeout", "120", "webapp:app"]
