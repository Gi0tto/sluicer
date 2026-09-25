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

# The first stage builds the wheel from the source it is given, and only that
# wheel is installed below: never a sluicer from PyPI, whose latest release is
# not necessarily the source being built.
FROM python:3.13-slim AS wheel

WORKDIR /src
# Only what the build reads. The .dockerignore says the same thing the other
# way round, so a context sent from a working tree carries no .venv or .git.
# NOTICE and LICENSES/ are named in pyproject.toml's license-files: without
# them the wheel was built with LICENSE alone, and the image shipped
# schema.org's and CLDR's data with neither their licences nor the notice
# that says which files they cover.
COPY pyproject.toml README.md LICENSE NOTICE ./
COPY LICENSES ./LICENSES
COPY src ./src
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /wheels .

FROM python:3.13-slim

ARG WITH_BROWSER=0
# The version the labels state. The build stops if the wheel says another, and
# a test holds this line to pyproject.toml.
ARG SLUICER_VERSION=0.8.0

LABEL org.opencontainers.image.title="Sluicer" \
      org.opencontainers.image.description="The data a web page declares, with where each value came from. No model, no API key." \
      org.opencontainers.image.source="https://github.com/Gi0tto/sluicer" \
      org.opencontainers.image.url="https://github.com/Gi0tto/sluicer" \
      org.opencontainers.image.documentation="https://gi0tto.github.io/sluicer/" \
      org.opencontainers.image.licenses="MIT AND CC-BY-SA-3.0 AND Unicode-3.0" \
      org.opencontainers.image.version="${SLUICER_VERSION}"

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright

COPY --from=wheel /wheels /wheels
# The licence files arrive twice on purpose: inside the installed package's
# metadata, where pip puts them, and here, where a person looking at the image
# finds them without knowing Python's layout.
COPY LICENSE NOTICE /usr/share/licenses/sluicer/
COPY LICENSES /usr/share/licenses/sluicer/LICENSES
COPY packaging/third_party.py /tmp/third_party.py

# The extras from the wheel built above, the browser only when asked for; then
# the licences of everything they bring, in THIRD-PARTY.txt beside Sluicer's:
# an image is a copy of every package in it, and BSD, MIT and Apache-2.0 ask
# for their text to go with a copy. The build stops if a package installed no
# licence file.
RUN wheel=$(ls /wheels/sluicer-*.whl) \
    && if [ "$WITH_BROWSER" = "1" ]; then extras='api,browser'; else extras='api'; fi \
    && pip install --no-cache-dir "${wheel}[${extras}]" \
    && rm -rf /wheels \
    && python /tmp/third_party.py /usr/share/licenses/sluicer/THIRD-PARTY.txt \
    && rm /tmp/third_party.py \
    && python -c "import sluicer, importlib.metadata as md; \
names = {f.name for f in md.files('sluicer') if 'licenses' in f.parts}; \
assert {'LICENSE', 'NOTICE', 'CC-BY-SA-3.0.txt', 'Unicode-3.0.txt'} <= names, names; \
assert sluicer.__version__ == '${SLUICER_VERSION}', (sluicer.__version__, '${SLUICER_VERSION}'); \
print('sluicer', sluicer.__version__, 'with', sorted(names))"

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
