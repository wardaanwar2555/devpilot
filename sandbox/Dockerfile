# Build:  docker build -t devpilot-sandbox -f sandbox/Dockerfile sandbox/
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
RUN pip install "pytest>=8,<9" && useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin runner
USER 10001
WORKDIR /work
