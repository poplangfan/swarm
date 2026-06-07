"""MCP (Model Context Protocol) — client for connecting to external MCP servers, server for exposing Swarm tools."""

from swarm.mcp.client import MCPClient
from swarm.mcp.server import SwarmMCPServer

__all__ = ["MCPClient", "SwarmMCPServer"]
