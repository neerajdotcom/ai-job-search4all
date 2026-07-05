"""`python -m mcp_server` entrypoint — runs the read-only run-history MCP server over stdio."""

from mcp_server.server import mcp

if __name__ == "__main__":
    mcp.run(transport="stdio")
