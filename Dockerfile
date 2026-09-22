# A Sluicer that can fetch, read and serve an agent, in one image.
#
# The base install is only lxml and click; this image takes the extras because
# an image nobody can fetch with is an image nobody wants.
#
# The browser is a build argument, because it is most of the image. Built as
# is, the image fetches with the plain HTTP rung only: a page that makes the
# ladder climb reaches a browser rung with no browser installed, and that climb
# fails. Build with the browser when you need it:
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

RUN pip install --no-cache-dir '.[fetch,markdown,mcp]' \
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
ENTRYPOINT []
CMD ["sluicer-mcp"]
