# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in Swarm, please report it privately.

**Do not open a public issue.** Instead, email the maintainers.

We will respond within 48 hours with:
- Confirmation of receipt
- An initial assessment of severity
- A timeline for resolution

## Supported Versions

| Version | Supported |
|---------|:---------:|
| 0.1.x   | ✅        |

## Security Considerations

### API Keys and Secrets

- Never commit `config.yaml` with real credentials
- Use `${ENV_VAR}` syntax in config for all secrets
- The `config.yaml` file should be in `.gitignore`

### Token Storage

- User OAuth tokens are encrypted at rest using AES-256-GCM
- The encryption key (`TOKEN_ENCRYPT_KEY`) must be kept secure
- Rotate encryption keys periodically

### LLM API Security

- API keys are never logged or stored in plaintext
- All LLM API calls use HTTPS
- Consider using API key rotation if supported by your provider

### Feishu Security

- App secrets should never be committed to version control
- Use environment variables for all Feishu credentials
- Regularly rotate app secrets
- Monitor the Feishu Open Platform audit log for suspicious activity

### Data Privacy

- Conversation data is stored locally in SQLite and ChromaDB
- ChromaDB collections are isolated per chat_id
- No conversation data is sent to external services (except the configured LLM)
- Enable audit logging for compliance requirements

### Dependency Security

- All dependencies are pinned in `pyproject.toml`
- Run `pip audit` periodically to check for known vulnerabilities
- Review dependency updates before upgrading

## Best Practices for Deployment

1. **Use a dedicated system user**: Run Swarm under a non-root account
2. **Set restrictive file permissions**: `chmod 600 config.yaml`
3. **Enable audit logging**: `audit_enabled: true` in config
4. **Use HTTPS**: For any exposed HTTP endpoints
5. **Keep logs secure**: Log files may contain conversation data
6. **Regular backups**: Back up `data/` directory
7. **Monitor error rates**: Set up alerts for unusual error patterns
