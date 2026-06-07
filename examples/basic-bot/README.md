# Basic Feishu Bot Example

Minimal Swarm bot setup with just an LLM.

## Files

- `config.yaml` — Minimal configuration
- `SOUL.md` — Bot personality

## Running

```bash
cd examples/basic-bot
swarm ws
```

## What It Does

- Responds to DMs and @mentions in groups
- Uses the LLM for general conversation
- No tools or special features enabled
- ~10 lines of configuration

## Configuration

```yaml
llm:
  api_key: "${LLM_API_KEY}"
  model: "deepseek-v4-pro"

feishu:
  app_id: "${FEISHU_APP_ID}"
  app_secret: "${FEISHU_APP_SECRET}"
```

That's it. Everything else uses defaults.
