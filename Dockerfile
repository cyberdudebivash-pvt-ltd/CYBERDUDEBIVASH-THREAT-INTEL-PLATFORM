# ============================================================================
# CYBERDUDEBIVASH® SENTINEL APEX — Production Dockerfile
# v47.1 CI DISK-SAFE BUILD (additive over v47.0)
#
# Changes (zero regression):
#   - Multi-stage build: builder → runtime (removes build toolchain from image)
#   - Non-root user: cdbuser (uid=1001) — CIS Docker Benchmark L1
#   - HEALTHCHECK: liveness probe wired to /api/v1/health
#   - Explicit EXPOSE 8080
#   - Deterministic pip install with --no-cache-dir --user
#   - Data/export dirs created before USER switch
#   - CMD switched to uvicorn (production ASGI) — CMD preserved as env override
#
# v47.1 FIX — CI/SBOM disk-space fix:
#   torch==2.2.0 (PyPI) pulls ~3GB of NVIDIA CUDA libs (nvidia-cublas-cu12,
#   libcublaslt.so.12, etc.) that exhaust GitHub Actions runner disk during
#   Docker image export. Root cause: pip auto-resolves CUDA extras for torch
#   on linux/amd64 even when no GPU is present.
#
#   ARG CPU_ONLY (default: false):
#     false → production build — full torch with GPU/CUDA support (unchanged)
#     true  → CI/SBOM build  — torch CPU-only wheel (~200MB vs ~3GB), no CUDA
#
#   CI workflow passes --build-arg CPU_ONLY=true. Production k8s/compose
#   builds pass nothing (default=false) — zero regression to production.
#
# Rollback: git revert this file — original CMD ["python", "-m", "agent.sentinel_blogger"]
#   available via SENTINEL_MODE=blogger env var override.
# ============================================================================

# ── Stage 1: Dependency Builder ───────────────────────────────────────────────
FROM python:3.12-slim AS builder

LABEL stage="builder"

WORKDIR /build

# Install build dependencies only in builder stage (never shipped to runtime)
RUN apt-get update -qq && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# CPU_ONLY=true  → CI/SBOM builds: torch CPU-only (~200MB, no CUDA libs)
# CPU_ONLY=false → Production builds: full torch with GPU support (default)
# NOTE: ARG must be declared AFTER FROM to be in scope for RUN.
ARG CPU_ONLY=false

COPY requirements.txt .

# Install to user site-packages (copied to runtime image).
# When CPU_ONLY=true: sed appends "+cpu" to whatever torch version is
# pinned in requirements.txt, in a temp copy of that file, then installs
# from the PyTorch CPU wheel index as the primary index (all other
# packages fall back to PyPI via --extra-index-url). This eliminates the
# ~3GB NVIDIA CUDA dependency chain that otherwise causes "no space left
# on device" in CI runners.
# v184.7 FIX: the previous sed hardcoded the literal string "2.2.0+cpu" as
# its replacement text, so a torch version bump in requirements.txt (e.g.
# fixing a CVE) would have been silently overwritten back to the old,
# vulnerable 2.2.0+cpu for every CPU_ONLY=true build -- defeating the
# fix specifically for CI/SBOM builds. Captures the actual version with a
# backreference instead of hardcoding one.
# v185.0 FIX: confirmed live (sbom-generation.yml run #423, 2026-09-03) --
# `pip install -r requirements.txt` failed with "Could not find a version
# that satisfies the requirement pydantic==2.13.4 (from versions: none)"
# even though that exact version is published and installs cleanly on
# retry -- a transient empty/stale response from the multi-index resolution
# (--index-url download.pytorch.org/whl/cpu + --extra-index-url pypi.org),
# not a bad pin. Every OTHER external network call in this same CI job
# (Docker Buildx setup, Syft install, Grype install; see sbom-generation
# .yml's own v47.4-v47.7 history) already has 3-attempt retry+backoff for
# exactly this transient-failure class -- this was the one unhardened one.
# Wraps only the two -r <requirements file> resolutions (the actual
# multi-package failure point); pip's own --upgrade pip bootstrap above is
# untouched. A persistent, non-transient failure still fails the build
# after 3 attempts, exactly as before.
RUN pip install --no-cache-dir --user --upgrade pip \
 && if [ "$CPU_ONLY" = "true" ]; then \
      echo "[BUILD] CPU_ONLY=true: installing torch CPU-only wheel (no CUDA)"; \
      sed -E 's|^torch==([0-9]+\.[0-9]+\.[0-9]+)|torch==\1+cpu|' \
          requirements.txt \
        > /tmp/req-cpu.txt; \
      for i in 1 2 3; do \
        pip install --no-cache-dir --user \
            --index-url https://download.pytorch.org/whl/cpu \
            --extra-index-url https://pypi.org/simple \
            -r /tmp/req-cpu.txt && break; \
        [ "$i" = 3 ] && { echo "[BUILD] pip install failed after 3 attempts"; exit 1; }; \
        echo "[BUILD] pip install attempt $i failed (transient index resolution), retrying in 15s..."; \
        sleep 15; \
      done; \
    else \
      echo "[BUILD] CPU_ONLY=false: installing full requirements (GPU/CUDA enabled)"; \
      for i in 1 2 3; do \
        pip install --no-cache-dir --user -r requirements.txt && break; \
        [ "$i" = 3 ] && { echo "[BUILD] pip install failed after 3 attempts"; exit 1; }; \
        echo "[BUILD] pip install attempt $i failed (transient index resolution), retrying in 15s..."; \
        sleep 15; \
      done; \
    fi


# ── Stage 2: Production Runtime ───────────────────────────────────────────────
FROM python:3.12-slim AS runtime

LABEL maintainer="CyberDudeBivash <bivash@cyberdudebivash.com>"
LABEL description="CDB-SENTINEL Threat Intelligence Platform — APEX ENTERPRISE"
LABEL version="47.0"
LABEL org.opencontainers.image.source="https://github.com/cyberdudebivash/CYBERDUDEBIVASH-THREAT-INTEL-PLATFORM"
LABEL org.opencontainers.image.vendor="CyberDudeBivash Pvt. Ltd."

# v48.0 SECURITY FIX: Apply all available OS patches to eliminate critical CVEs
# in the python:3.12-slim base image (e.g., openssl, libssl, libexpat, glibc).
# This runs apt-get upgrade in the runtime stage so the SHIPPED image is fully
# patched. The SBOM build (CPU_ONLY=true) also benefits since it copies this stage.
RUN apt-get update -qq \
 && apt-get upgrade -y --no-install-recommends \
 && rm -rf /var/lib/apt/lists/*

# Security: create non-root service account (CIS Docker Benchmark L1 compliance)
RUN groupadd -r cdbuser --gid=1001 \
 && useradd -r -g cdbuser --uid=1001 \
    --no-create-home \
    --shell=/sbin/nologin \
    --comment="CDB SENTINEL APEX Service Account" \
    cdbuser

WORKDIR /app

# Copy compiled dependencies from builder (no build toolchain in runtime)
COPY --from=builder /root/.local /home/cdbuser/.local

# Copy application code — chown to service account
COPY --chown=cdbuser:cdbuser agent/       ./agent/
COPY --chown=cdbuser:cdbuser requirements.txt .

# Create required runtime directories and set ownership
RUN mkdir -p \
    data/stix \
    data/whitepapers \
    data/archive \
    data/security \
    data/observability \
    data/tenants \
    data/orgs \
    exports \
    logs \
 && chown -R cdbuser:cdbuser \
    data/ \
    exports/ \
    logs/ \
 && chmod 750 data/ exports/ logs/

# Runtime environment
ENV PYTHONPATH=/app
ENV PATH="/home/cdbuser/.local/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# ── Health Check ──────────────────────────────────────────────────────────────
# Liveness probe: checks /api/v1/health endpoint
# - Interval: 30s (allows startup time)
# - Timeout: 5s (fail fast)
# - Start period: 20s (grace period during initial startup)
# - Retries: 3 (before marking unhealthy)
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "\
import urllib.request, sys; \
try: \
    r = urllib.request.urlopen('http://localhost:8080/api/v1/health', timeout=4); \
    sys.exit(0 if r.status in (200, 503) else 1) \
except Exception as e: \
    print(f'Health check failed: {e}', file=sys.stderr); sys.exit(1)"

# Drop privileges — run as non-root service account
USER cdbuser

EXPOSE 8080

# ── Startup Command ───────────────────────────────────────────────────────────
# Default: FastAPI/uvicorn production server
# Override with SENTINEL_MODE=blogger to run the intelligence pipeline
CMD ["sh", "-c", "\
  if [ \"${SENTINEL_MODE}\" = \"blogger\" ]; then \
    exec python -m agent.sentinel_blogger; \
  else \
    exec uvicorn agent.api.api_server:app \
      --host 0.0.0.0 \
      --port 8080 \
      --workers 2 \
      --access-log \
      --log-level info \
      --proxy-headers \
      --forwarded-allow-ips='*'; \
  fi"]
