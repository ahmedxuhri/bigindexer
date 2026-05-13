FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    git ca-certificates && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir bigindexer==0.1.1

RUN echo '{"units":[],"edges":[],"clusters":[]}' > bgi-graph.json && \
    echo '{"edges":[]}' > fuse-graph.json

CMD ["bgi", "mcp", "--graph", "bgi-graph.json", "--fuse-graph", "fuse-graph.json"]
