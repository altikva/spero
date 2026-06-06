# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Build stage: build and install the CURRENT spero source into a clean venv.
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS build

# uv: fast, reproducible installs. Pinned for repeatable builds.
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /uvx /usr/local/bin/

ENV UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /src

# Create an isolated venv that the final stage will copy verbatim.
RUN uv venv /opt/venv --python python3.12
ENV VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:${PATH}"

# Copy only what the build backend (hatchling) needs to produce the wheel.
COPY pyproject.toml README.md LICENSE NOTICE ./
COPY uv.lock ./
COPY src ./src

# Install plain spero (no extras): the k8s provider shells out to kubectl,
# so the python kubernetes client is not needed in-cluster. Build from the
# local source so the image carries the CURRENT code, not the PyPI release.
RUN uv pip install --python /opt/venv .

# ---------------------------------------------------------------------------
# Final stage: minimal runtime with the venv + a pinned kubectl, non-root.
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

# Pinned kubectl. Bump KUBECTL_VERSION and KUBECTL_SHA256 together.
# sha256 from https://dl.k8s.io/release/v1.31.4/bin/linux/amd64/kubectl.sha256
# Target linux/amd64 deliberately (the common cluster node arch). To build a
# native arm64 image, override KUBECTL_ARCH=arm64 with the matching sha256 from
# https://dl.k8s.io/release/v1.31.4/bin/linux/arm64/kubectl.sha256
ARG KUBECTL_VERSION=v1.31.4
ARG KUBECTL_SHA256=298e19e9c6c17199011404278f0ff8168a7eca4217edad9097af577023a5620f
ARG KUBECTL_ARCH=amd64

# curl is needed only to fetch kubectl; remove it afterwards to stay lean.
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends curl ca-certificates; \
    curl -fsSL -o /usr/local/bin/kubectl \
        "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/${KUBECTL_ARCH}/kubectl"; \
    echo "${KUBECTL_SHA256}  /usr/local/bin/kubectl" | sha256sum -c -; \
    chmod 0755 /usr/local/bin/kubectl; \
    kubectl version --client=true; \
    apt-get purge -y --auto-remove curl; \
    rm -rf /var/lib/apt/lists/*

# Bring in the prebuilt venv from the build stage.
COPY --from=build /opt/venv /opt/venv

ENV VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:/usr/local/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Non-root runtime user. uid 65532 matches the common distroless "nonroot".
RUN groupadd --gid 65532 nonroot \
    && useradd --uid 65532 --gid 65532 --no-create-home --shell /usr/sbin/nologin nonroot
USER 65532:65532

ENTRYPOINT ["spero"]
CMD ["watch"]
