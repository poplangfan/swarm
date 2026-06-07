"""Auth middleware — request-level token injection for the agent."""

from __future__ import annotations

from dataclasses import replace

from swarm.agent.context import RequestContext
from swarm.auth.token_store import TokenStore


async def inject_user_token(
    ctx: RequestContext,
    token_store: TokenStore,
) -> RequestContext:
    """Inject user_access_token into a RequestContext if available.

    If the user has authorized, adds their token. If not, leaves it as None.
    The tools layer checks ctx.user_token to decide whether to operate
    with user identity or app identity.
    """
    if ctx.user_token:
        return ctx  # Already has a token

    token = token_store.lookup(ctx.user_id)
    if token and not token.is_expired():
        return replace(ctx, user_token=token.access_token)

    return ctx  # No valid token available


async def check_authorization(
    ctx: RequestContext,
    token_store: TokenStore,
    oauth,
) -> tuple[RequestContext, str | None]:
    """Check if user is authorized. Returns (updated_context, auth_message).

    If unauthorized, returns an auth_message with the OAuth URL.
    If authorized with valid token, returns updated context with token injected.
    """
    token = token_store.lookup(ctx.user_id)

    if not token:
        # User hasn't authorized yet — return auth URL
        auth_url = oauth.get_authorization_url(state=ctx.user_id)
        auth_msg = (
            f"Hi! To use document and file features, please authorize first:\n\n"
            f"[Click here to authorize]({auth_url})\n\n"
            f"After authorizing, send me another message to continue."
        )
        return ctx, auth_msg

    if token.is_expired():
        # Try to refresh
        refreshed = await oauth.refresh_access_token(ctx.user_id)
        if not refreshed:
            # Refresh failed — ask user to re-authorize
            auth_url = oauth.get_authorization_url(state=ctx.user_id)
            return ctx, f"Your authorization has expired. Please [re-authorize]({auth_url})."
        token = refreshed

    return replace(ctx, user_token=token.access_token), None
