# syntax=docker/dockerfile:1
# Build: docker build -t dagobert .
# No architecture here: `docker buildx build --platform linux/amd64,linux/arm64` works as is.

# The Python of CI (.python-version). Dependabot raises tag and digest together.
FROM python:3.14.8-slim-trixie@sha256:a2b82f3c48559aa0a8446d9af49826b6e2b2016f4cd2afabfe6013ec53729170 AS python
# A stage, not `COPY --from=<image>`, so that Dependabot sees the pin.
FROM ghcr.io/astral-sh/uv:0.13.5@sha256:32a7bb39b496babbd997b0a39a4d66c126bdaf5661b302bf6f06abda8deca6ff AS uv

FROM python AS build
COPY --from=uv /uv /usr/local/bin/uv
# Bytecode at build time: the runtime cannot write into the venv. No managed Python: the venv
# must point to /usr/local/bin/python3 of the same base image in the final stage.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_DEV=1 \
    UV_PYTHON_DOWNLOADS=0
WORKDIR /app
# Dependencies first: this layer stays cached while only the source changes.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-editable
COPY pyproject.toml uv.lock ./
COPY src ./src
# --no-editable: the package goes into site-packages as a wheel, so /app/src is not needed later.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-editable

FROM python
# Fixed UID/GID: a bind mount needs the same owner on the host, or `user:` in compose.
RUN groupadd --system --gid 10001 dagobert \
    && useradd --system --no-log-init --uid 10001 --gid dagobert --create-home \
        --shell /usr/sbin/nologin dagobert \
    && install -d -o dagobert -g dagobert -m 0750 /data
COPY --from=build /app/.venv /app/.venv
# Hiding the welcome message also stops the lookup of the external IP address
# (checkip.amazonaws.com) that Streamlit makes at start on a wildcard address.
# glibc gives a block of 1 MiB or more back to the system when it is freed: by default the
# threshold rises to 32 MiB, and the freed arrays of the runs stayed in the arenas of the
# script threads, about 0.5 GB of the main process.
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    DAGOBERT_DATA=/data \
    DAGOBERT_ADDRESS=0.0.0.0 \
    DAGOBERT_BROWSER=false \
    STREAMLIT_SERVER_FILE_WATCHER_TYPE=none \
    STREAMLIT_LOGGER_HIDE_WELCOME_MESSAGE=true \
    GLIBC_TUNABLES=glibc.malloc.mmap_threshold=1048576
# Numeric, so that a runtime can check `runAsNonRoot` without the passwd file.
USER 10001:10001
# `dagobert run scenarios/x.yaml` resolves against /data and writes the report to /data/out.
WORKDIR /data
VOLUME /data
EXPOSE 8321
# The health route follows the port and the base URL path of the deployment. No curl in slim.
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --start-interval=2s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request as u; b = os.environ.get('STREAMLIT_SERVER_BASE_URL_PATH', '').strip('/'); u.urlopen('http://127.0.0.1:%s/%s_stcore/health' % (os.environ.get('DAGOBERT_PORT', '8321'), b + '/' if b else ''), timeout=4)"]
ENTRYPOINT ["dagobert"]
CMD ["app"]
