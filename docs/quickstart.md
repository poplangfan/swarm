# Quickstart Guide

Get Swarm running in 5 minutes.

## Prerequisites

- Python 3.10 or later
- A Feishu account with app creation permissions
- An LLM API key (DeepSeek, OpenAI, or Anthropic)

## 1. Install Swarm

```bash
pip install swarm-agent
# or from source:
git clone https://github.com/your-org/swarm.git
cd swarm
pip install -e .
```

## 2. Create Configuration

```bash
swarm init
```

This creates `config.yaml` in your current directory. Edit it with your credentials:

```yaml
llm:
  provider: "anthropic"
  base_url: "https://api.deepseek.com/anthropic"
  api_key: "sk-your-deepseek-key"
  model: "deepseek-v4-pro"

feishu:
  app_id: "cli_xxxxxxxxxxxx"
  app_secret: "your_app_secret"
```

## 3. Test in CLI Mode

```bash
swarm chat
```

You should see:

```
   _____
  / ___/      __  ______ ___  ____ ___  ___
  \__ \| | /| / / / __ `__ \/ __ `__ \/ _ \
 ___/ /| |/ |/ / / / / / / / / / / / /  __/
/____/ |__/|__/ /_/ /_/ /_/_/ /_/ /_/\___/

Swarm Chat — session: default
Type /help for commands, /exit to quit

you > Hello!
Swarm > Hello! How can I help you today?
```

## 4. Set Up Feishu App

1. Go to [Feishu Open Platform](https://open.feishu.cn/)
2. Create a new "Enterprise Self-built App"
3. Under "Features" → "Bot": Enable bot capability
4. Under "Permissions": Add `im:message` and `im:message:receive_as_bot`
5. Under "Event Subscriptions": Subscribe to `im.message.receive_v1`
6. Get your App ID and App Secret from "Credentials"

Add them to `config.yaml`:

```yaml
feishu:
  app_id: "cli_xxxxxxxxxxxx"
  app_secret: "your_secret"
```

## 5. Start Feishu Bot

```bash
swarm ws
```

Your bot is now live! Send a message to it in Feishu to test.

## 6. Enable User Authorization (Optional)

If you want users to operate documents and files with their own identity:

1. Add OAuth redirect URL in Feishu Open Platform (use a LAN IP like `http://192.168.1.100:9876/oauth/callback`)
2. Enable auth in config:

```yaml
auth:
  enabled: true
  redirect_uri: "http://192.168.1.100:9876/oauth/callback"
  token_encrypt_key: "${TOKEN_ENCRYPT_KEY}"
```

Users will automatically receive an authorization link on their first message.

## Next Steps

- [Configuration Guide](configuration.md) — All configuration options
- [Architecture Guide](architecture.md) — System design deep-dive
- [Writing Skills](skills.md) — Create custom agent behaviors
- [Feishu Setup](feishu-setup.md) — Detailed Feishu app configuration
- [Deployment Guide](deployment.md) — Production deployment
