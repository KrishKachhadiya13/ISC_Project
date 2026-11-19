# Multi-stage build: CPU-only PyTorch in the runtime image (the app never trains).
FROM python:3.13-slim AS builder
WORKDIR /build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
COPY requirements.txt .
# pySTC is a small C++ extension and is compiled only in this disposable build stage.
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential git \
 && rm -rf /var/lib/apt/lists/*
# Install the small CPU wheel of torch first so requirements.txt does not pull CUDA.
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install torch --index-url https://download.pytorch.org/whl/cpu \
 && /opt/venv/bin/pip install -r requirements.txt

FROM python:3.13-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PATH="/opt/venv/bin:$PATH" \
    OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2
# Run as an unprivileged user; the server never writes to disk.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libstdc++6 \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --create-home --uid 10001 stegaguard
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY app ./app
COPY models ./models
COPY results ./results
USER stegaguard
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
