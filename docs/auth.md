# Authentication & Authorization

Swarm supports two levels of authentication for Feishu operations.

## App-Level Authentication

**Default mode.** The bot operates with the app's own identity.

```
Bot sends message → uses tenant_access_token → operates as "Swarm Bot"
```

- No user setup required
- Limited to permissions granted to the app
- Works for all message operations
- Cannot access user-specific resources (documents, drives, calendars)

## User-Level Authentication (OAuth)

**Advanced mode.** The bot operates with each user's individual identity.

```
User A sends message → uses user A's access_token → sees only A's documents
User B sends message → uses user B's access_token → sees only B's documents
```

### How It Works

1. User sends their first message to the bot
2. If auth is enabled and user hasn't authorized:
   - Bot returns an OAuth authorization link
   - "Please click to authorize: [link]"
3. User clicks the link in their browser
4. Feishu shows the permission consent screen
5. User approves → Feishu redirects to Swarm's callback server
6. Swarm exchanges the authorization code for tokens
7. Tokens are encrypted and stored
8. Bot notifies: "Authorization successful!"
9. On subsequent messages, the token is automatically injected

### Token Management

- **access_token**: Valid 2 hours, used for API calls
- **refresh_token**: Long-lived, used to get new access_tokens
- **Auto-refresh**: Expired tokens are refreshed automatically
- **Encrypted storage**: AES-256-GCM encryption at rest
- **Re-authorization**: If refresh fails, user is prompted to re-authorize

### Group Chat Behavior

In group chats, Swarm uses the message sender's identity:

```
group message from User A → operates as User A
group message from User B → operates as User B
```

If a sender hasn't authorized, the bot falls back to app-level permissions for that specific message.

## Configuration

```yaml
auth:
  enabled: true
  redirect_uri: "http://192.168.1.100:9876/oauth/callback"
  token_encrypt_key: "${TOKEN_ENCRYPT_KEY}"
  scopes:
    - "im:message"
    - "drive:drive:read"
    - "docx:document:read"
```

### Setting TOKEN_ENCRYPT_KEY

Generate a strong key:

```bash
python -c "import secrets; print(secrets.token_hex(16))"
```

Add to your environment or config:

```bash
export TOKEN_ENCRYPT_KEY="your-generated-hex-key"
```

## Redirect URI Notes

The OAuth redirect happens in the **user's browser**, not server-to-server. This means:

- `localhost` works for development
- LAN IP addresses work for office networks
- No public IP or domain required
- No HTTPS required (unlike webhook URLs)

For wider deployment, use a machine IP that users' browsers can reach.

## Permission Scopes

Request only the scopes you actually need:

| Scope | Required For |
|-------|-------------|
| `im:message` | Sending/receiving messages (required) |
| `drive:drive:read` | Listing and reading user's Drive files |
| `docx:document:read` | Reading user's documents |
| `docx:document:write` | Creating/editing user's documents |
| `calendar:calendar:read` | Reading user's calendar |
| `calendar:calendar:write` | Creating calendar events |
| `contact:contact:read` | Reading user's contacts |

## Security Considerations

- **Encrypt tokens at rest**: Always set a strong `TOKEN_ENCRYPT_KEY`
- **Minimize scopes**: Request only necessary permissions
- **Token rotation**: Refresh tokens are rotated on each use (Feishu default)
- **Audit logging**: Enable `audit_enabled: true` to track authorization events
- **Data isolation**: User tokens are never shared between users
