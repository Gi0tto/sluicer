# A Sluicer that can fetch, read, and serve an agent or any HTTP client, in one
# image.
#
# The base install fetches over plain HTTP; this image adds the markdown, MCP
# and HTTP API extras, so that one image serves every door.
#
# The browser is a build argument, because it is most of the image. Built as
# is, the image fetches with the plain HTTP rung only: a page that makes the
# ladder climb reaches a browser rung that is not installed, the climb fails,
# and the HTTP page comes back saying so. Build with the browser -- the
# `browser` extra and its Chromium -- when you need it:
#   docker build --build-arg WITH_BROWSER=1 -t sluicer .
FROM python:3.13-slim

ARG WITH_BROWSER=0

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright

WORKDIR /app
# Only what the build reads. The .dockerignore says the same thing the other
# way round, so a context sent from a working tree carries no .venv or .git.
COPY pyproject.toml README.md LICENSE ./
COPY src ./src

RUN if [ "$WITH_BROWSER" = "1" ]; then extras='api,browser'; else extras='api'; fi \
    && pip install --no-cache-dir ".[$extras]" \
    && python -c "import sluicer; print('sluicer', sluicer.__version__)"

# Chromium's system libraries arrive through apt, so this runs as root, before
# the switch below, and into a path the unprivileged user can read.
RUN if [ "$WITH_BROWSER" = "1" ]; then \
        playwright install --with-deps chromium \
        && rm -rf /var/lib/apt/lists/*; \
    fi

# Nothing here needs root at run time, so nothing runs as root.
RUN useradd --create-home --uid 10001 sluicer
USER sluicer

# The MCP server speaks over stdio, so this is the useful default: an agent runs
# the container and talks to it. Override the command for the CLI:
#   docker run --rm sluicer sluicer extract https://example.com
# or for the HTTP API, which inside a container has to listen on every
# interface, and so will not start without a token:
#   docker run --rm -p 127.0.0.1:8000:8000 -e SLUICER_API_TOKEN="$token" \
#     sluicer sluicer serve --host 0.0.0.0
EXPOSE 8000
ENTRYPOINT []
CMD ["sluicer-mcp"]
