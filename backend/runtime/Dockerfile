# replic8 legacy runtime: COBOL and Fortran compilers plus the call shim.
# Build: docker build -t replic8-legacy-runtime:1 backend/runtime
# Pin the base image by digest before the demo (docs/security.md, known gaps).
# Behind an HTTPS-only proxy (like Claude cloud sessions), apt needs https sources
# and the proxy CA; do that in a throwaway build context, not in this file.
FROM ubuntu:24.04

RUN apt-get update \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends gnucobol3 gfortran python3 \
 && rm -rf /var/lib/apt/lists/*

COPY shim.py build.py /replic8/
RUN chmod 0444 /replic8/*.py

USER 65534:65534
WORKDIR /app
