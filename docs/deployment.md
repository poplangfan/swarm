# Deployment Guide

Deploy Swarm in production for your Feishu organization.

## System Requirements

- Linux (Ubuntu 20.04+, CentOS 8+, Debian 11+)
- Python 3.10 or later
- 1GB RAM minimum (2GB recommended)
- 1GB disk space (plus log retention)
- Network access to Feishu API (`open.feishu.cn` or `open.larksuite.com`)

## Docker Deployment (Recommended)

### Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY . .
RUN pip install -e .

RUN mkdir -p /app/data/logs /app/data/chroma
VOLUME ["/app/data", "/app/config"]

ENTRYPOINT ["swarm", "ws"]
```

### Docker Compose

```yaml
version: "3.8"
services:
  swarm:
    build: .
    restart: unless-stopped
    volumes:
      - ./config.yaml:/app/config.yaml:ro
      - ./data:/app/data
    environment:
      - LLM_API_KEY=${LLM_API_KEY}
      - FEISHU_APP_ID=${FEISHU_APP_ID}
      - FEISHU_APP_SECRET=${FEISHU_APP_SECRET}
      - TOKEN_ENCRYPT_KEY=${TOKEN_ENCRYPT_KEY}
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

### Run

```bash
docker compose up -d
docker compose logs -f
```

## Manual Deployment

### 1. Clone and Install

```bash
git clone https://github.com/your-org/swarm.git /opt/swarm
cd /opt/swarm
python -m venv venv
source venv/bin/activate
pip install -e .
```

### 2. Configure

```bash
cp config.yaml.example config.yaml
# Edit with your credentials
vim config.yaml
```

### 3. Systemd Service

Create `/etc/systemd/system/swarm.service`:

```ini
[Unit]
Description=Swarm Feishu AI Agent
After=network.target

[Service]
Type=simple
User=swarm
Group=swarm
WorkingDirectory=/opt/swarm
Environment=LLM_API_KEY=your-key
Environment=FEISHU_APP_ID=cli_xxx
Environment=FEISHU_APP_SECRET=your-secret
Environment=TOKEN_ENCRYPT_KEY=your-encrypt-key
ExecStart=/opt/swarm/venv/bin/swarm ws
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo useradd -r -s /bin/false swarm
sudo chown -R swarm:swarm /opt/swarm
sudo systemctl daemon-reload
sudo systemctl enable --now swarm
sudo systemctl status swarm
```

### 4. Supervisor

Alternative process manager:

```ini
[program:swarm]
command=/opt/swarm/venv/bin/swarm ws
directory=/opt/swarm
user=swarm
autostart=true
autorestart=true
stderr_logfile=/var/log/swarm/error.log
stdout_logfile=/var/log/swarm/output.log
environment=LLM_API_KEY="your-key",FEISHU_APP_ID="cli_xxx"
```

## Health Checks

Swarm doesn't expose an HTTP endpoint by default. Monitor via:

### Process Check
```bash
systemctl is-active swarm
```

### Log Monitoring
```bash
tail -f /opt/swarm/data/logs/swarm-$(date +%Y-%m-%d).log
```

### Heartbeat Cron
Configure a cron job to verify the bot responds:

```yaml
cron:
  jobs:
    heartbeat:
      interval_minutes: 15
```

## Log Management

Logs are stored in `./data/logs/`:

```
swarm-2026-06-07.log       # Today's logs
swarm-2026-06-06.log.gz    # Yesterday (compressed)
audit-2026-06-07.log       # Audit trail
errors-2026-06-07.log      # Error log (separated)
```

### Log Rotation

- Daily rotation at midnight
- Automatic gzip compression
- Retention configurable (default: 30 days)
- Audit logs retained 2x longer

### External Log Aggregation

Enable JSON logging and ship to your aggregator:

```yaml
logging:
  json_format: true
```

## Monitoring

### Key Metrics

Monitor these signals for production health:
- Process uptime (systemd/supervisor)
- Log error rate (grep ERROR count per hour)
- LLM API latency (from structured logs)
- Disk usage (log and data directories)
- Memory usage

### Alerting

Set up alerts for:
1. Process crash (systemd should auto-restart)
2. LLM API returning >5% errors
3. Disk usage >80%
4. Logs not rotating (disk filling up)

## Upgrading

```bash
cd /opt/swarm
git pull
source venv/bin/activate
pip install -e . --upgrade
sudo systemctl restart swarm
```

## Backup

Essential files to back up:
- `data/sessions.db` — Conversation history
- `data/tokens.db` — User OAuth tokens (encrypted)
- `data/chroma/` — Vector memory store
- `config.yaml` — Configuration

Example backup script:
```bash
#!/bin/bash
tar czf swarm-backup-$(date +%Y%m%d).tar.gz \
  config.yaml \
  data/sessions.db \
  data/tokens.db \
  data/chroma/
```
