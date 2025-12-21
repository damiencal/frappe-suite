# Frappe Press with Shared Bench Multi-tenancy Support
# Build: docker build -t ghcr.io/damiencal/frappe-press:v15-shared -f Containerfile .

ARG FRAPPE_VERSION=v15
ARG PYTHON_VERSION=3.11

FROM frappe/bench:latest AS builder

ARG FRAPPE_VERSION

# Get frappe and press
RUN bench init --skip-redis-config-generation --frappe-branch ${FRAPPE_VERSION} /home/frappe/frappe-bench

WORKDIR /home/frappe/frappe-bench

# Copy our modified press into the apps directory
COPY --chown=frappe:frappe . /home/frappe/frappe-bench/apps/press

# Install press app dependencies
RUN /home/frappe/frappe-bench/env/bin/pip install -e /home/frappe/frappe-bench/apps/press

# Install kubernetes Python client for shared bench mode
RUN /home/frappe/frappe-bench/env/bin/pip install kubernetes

# Production image
FROM frappe/frappe-worker:${FRAPPE_VERSION}

# Copy bench from builder
COPY --from=builder --chown=frappe:frappe /home/frappe/frappe-bench /home/frappe/frappe-bench

WORKDIR /home/frappe/frappe-bench

# Set environment
ENV FRAPPE_SITE_NAME_HEADER=Host

# The base image handles the entrypoint
