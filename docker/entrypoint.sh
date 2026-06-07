#!/bin/bash
set -e

# Verify config exists
if [ ! -f "/app/config.yaml" ]; then
    echo "ERROR: config.yaml not found. Mount your config to /app/config.yaml"
    exit 1
fi

# Verify required env vars
if [ -z "$LLM_API_KEY" ]; then
    echo "WARNING: LLM_API_KEY not set. Some providers may not work."
fi

if [ -z "$FEISHU_APP_ID" ] || [ -z "$FEISHU_APP_SECRET" ]; then
    echo "ERROR: FEISHU_APP_ID and FEISHU_APP_SECRET must be set"
    exit 1
fi

if [ -z "$TOKEN_ENCRYPT_KEY" ]; then
    echo "ERROR: TOKEN_ENCRYPT_KEY must be set for OAuth token encryption"
    exit 1
fi

echo "Starting Swarm..."
exec swarm ws --config /app/config.yaml
