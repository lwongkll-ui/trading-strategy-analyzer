# Stock Selection — page builder image.
#
# Build context is the REPO ROOT (see docker-compose.yml), because the app reads
# its constituent CSVs from REPO_ROOT/stock_tool/resources relative to
# stock_select/ — both trees must exist inside the image at the same layout.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Asia/Hong_Kong

# tzdata lets the daily "21:00 HKT" schedule in refresh-loop.sh resolve the zone.
RUN apt-get update && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

# Dependencies first, for layer caching. curl_cffi is required by modern
# yfinance to obtain Yahoo's auth crumb (browser impersonation) — without it
# every .info returns a 401 and all fundamentals go blank.
COPY stock_select/requirements.txt /app/stock_select/requirements.txt
RUN pip install -r /app/stock_select/requirements.txt curl_cffi

# App code + the shared constituent CSVs, mirroring the repo layout so
# config.py's REPO_ROOT/stock_tool/resources path resolves inside the container.
COPY stock_select/ /app/stock_select/
COPY stock_tool/resources/ /app/stock_tool/resources/

# Strip any CRLF the script may have picked up on a Windows checkout, otherwise
# /bin/sh fails with a "bad interpreter" error, then make it executable.
RUN sed -i 's/\r$//' /app/stock_select/docker/refresh-loop.sh \
    && chmod +x /app/stock_select/docker/refresh-loop.sh
WORKDIR /app/stock_select
CMD ["/app/stock_select/docker/refresh-loop.sh"]
