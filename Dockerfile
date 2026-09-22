# A Sluicer that can fetch, read and serve an agent, in one image.
#
# The base install is only lxml and click; this image takes the extras because
# an image nobody can fetch with is an image nobody wants.
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY . /app

RUN pip install --no-cache-dir '.[fetch,markdown,mcp]' \
    && python -c "import sluicer; print('sluicer', sluicer.__version__)"

# The MCP server speaks over stdio, so this is the useful default: an agent runs
# the container and talks to it. Override the command for the CLI:
#   docker run --rm sluicer sluicer extract https://example.com
ENTRYPOINT []
CMD ["sluicer-mcp"]
