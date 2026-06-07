# Feishu App Setup Guide

Detailed instructions for creating and configuring a Feishu app for Swarm.

## Step 1: Create App

1. Visit [Feishu Open Platform](https://open.feishu.cn/)
2. Click "Create App" → "Enterprise Self-built App"
3. Name your app (e.g., "Swarm Assistant")
4. Add a description and icon

## Step 2: Enable Bot

1. In the left sidebar, click "Features" → "Bot"
2. Toggle "Enable Bot" to ON
3. Configure bot name and description
4. Save

## Step 3: Configure Permissions

Go to "Permissions" and add:

### Required Permissions
| Permission | Description |
|-----------|-------------|
| `im:message` | Send and receive messages |
| `im:message:receive_as_bot` | Receive group chat messages |

### Optional Permissions (for document features)
| Permission | Description |
|-----------|-------------|
| `drive:drive:read` | Read files from user's Drive |
| `docx:document:read` | Read user's documents |
| `calendar:calendar:read` | Read calendar events |

After adding permissions, click "Publish" to apply changes. Administrators will need to approve.

## Step 4: Event Subscriptions

1. Go to "Event Subscriptions"
2. Enable event subscriptions
3. Subscribe to: `im.message.receive_v1`
4. For WebSocket mode, you don't need to configure a Request URL

## Step 5: OAuth (optional)

For user-level document access:

1. Go to "Security" → "OAuth 2.0"
2. Add a redirect URL (e.g., `http://192.168.1.x:9876/oauth/callback`)
   - Use a LAN IP if running on the same network as users
   - The redirect happens in the user's browser, not server-to-server
3. Save

## Step 6: Get Credentials

Go to "Credentials" and copy:
- **App ID**: Starts with `cli_`
- **App Secret**: Long random string

## Step 7: Publish App

1. Click "Publish" in the top-right
2. Create a new version
3. Administrators approve the app
4. The app is now live

## WebSocket vs Webhook

Swarm uses **WebSocket** mode exclusively. This means:

| WebSocket | Webhook |
|-----------|---------|
| ✅ No public IP needed | ❌ Requires public IP |
| ✅ No domain/HTTPS needed | ❌ Requires HTTPS |
| ✅ Works behind NAT/firewall | ❌ Requires port forwarding |
| ✅ Client connects to Feishu | ❌ Feishu connects to you |

No webhook URL configuration is needed.

## Testing

1. In Feishu, find your bot by name
2. Send a direct message: "Hello"
3. Add the bot to a group and @mention it
4. The bot should respond

## Troubleshooting

**Bot doesn't respond to DMs**
- Check that Bot capability is enabled
- Verify `im:message` permission is granted
- Check the logs: `./data/logs/swarm-*.log`

**Bot doesn't respond in groups**
- Check `group_policy` in config — set to "mention" or "open"
- Verify `im:message:receive_as_bot` permission
- @mention the bot in the group

**WebSocket won't connect**
- Verify app_id and app_secret are correct
- Check network connectivity to `open.feishu.cn`
- Check logs for specific error messages

**OAuth not working**
- Ensure redirect URL matches exactly what's configured
- The redirect happens in the browser — make sure the callback server is reachable from the user's browser
- Check `TOKEN_ENCRYPT_KEY` is set
