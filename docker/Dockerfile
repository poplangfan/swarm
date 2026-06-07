FROM python:3.11-slim

LABEL org.opencontainers.image.title="Swarm"
LABEL org.opencontainers.image.description="Feishu AI Agent Framework"
LABEL org.opencontainers.image.version="0.1.0"

WORKDIR /app

# Copy project files (README.md required by hatchling for pip install)
COPY pyproject.toml README.md ./
COPY swarm/ swarm/
COPY skills_builtin/ skills_builtin/

# Install Python dependencies
RUN pip install --no-cache-dir -e .

# Create data directories
RUN mkdir -p /app/data/logs /app/data/chroma

VOLUME ["/app/data", "/app/config"]

ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["swarm", "ws"]
