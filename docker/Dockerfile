FROM python:3.11-slim

LABEL org.opencontainers.image.title="Swarm"
LABEL org.opencontainers.image.description="Feishu AI Agent Framework"
LABEL org.opencontainers.image.version="0.1.0"

WORKDIR /app

# Copy project files (README.md required by hatchling for pip install)
COPY pyproject.toml README.md ./
COPY agent/ agent/
COPY auth/ auth/
COPY bus/ bus/
COPY cli/ cli/
COPY config/ config/
COPY cron/ cron/
COPY delivery/ delivery/
COPY events/ events/
COPY gateway/ gateway/
COPY logging_/ logging_/
COPY mcp/ mcp/
COPY memory/ memory/
COPY plugins/ plugins/
COPY providers/ providers/
COPY session/ session/
COPY skills/ skills/
COPY state/ state/
COPY tools/ tools/
COPY utils/ utils/
COPY version.py ./
COPY skills_builtin/ skills_builtin/

# Install Python dependencies
RUN pip install --no-cache-dir -e .

# Create data directories
RUN mkdir -p /app/data/logs /app/data/chroma

VOLUME ["/app/data", "/app/config"]

ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["swarm", "ws"]
