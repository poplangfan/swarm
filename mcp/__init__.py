"""MCP (Model Context Protocol) — client for connecting to external MCP servers, server for exposing Swarm tools."""

from mcp.client import MCPClient
from mcp.server import SwarmMCPServer

__all__ = ["MCPClient", "SwarmMCPServer"]
