# mcp_server/ — read-only run-history access for Claude Desktop/Code

Deep docs for `mcp_server/` (`server.py`, `__main__.py`). Loads when working
in `mcp_server/`. High-level overview is in the root `CLAUDE.md`.

`mcp_server/` exposes the same `storage/run_store.py` functions the webapp dashboard uses — `list_runs()`, `load_run(run_id)`, `compute_stats()` — as MCP tools, so you can ask Claude Desktop or Claude Code things like "what was my best match this week?" directly instead of browsing `/runs`. It's read-only, reads the same `data/runs/*.json` files, requires **no new credentials**, and runs locally over stdio — it doesn't touch `main.py` or any of the pipeline's scrape/score/optimize/email integrations.

- **Run:** `pip install -r requirements.txt` then `python -m mcp_server` (stdio transport — not meant to be run standalone in a terminal; point an MCP client at it instead).
- **Connect from Claude Desktop/Code:** add an entry pointing at `python -m mcp_server` with `cwd` set to this repo, e.g. (Claude Desktop `claude_desktop_config.json`):
  ```json
  {
    "mcpServers": {
      "job-search-history": {
        "command": "python",
        "args": ["-m", "mcp_server"],
        "cwd": "/absolute/path/to/job-search-agent"
      }
    }
  }
  ```
- **Tools:** `list_runs` (summaries, newest first), `load_run(run_id)` (full snapshot incl. `jobs[]`; returns `None` for an unknown/invalid `run_id` — same path-traversal guard as the webapp's `load_run`), `compute_stats` (same aggregates the home page's charts use).
- This is purely additive/optional — **not** a replacement for the Adzuna/Groq/Gemini/Gmail integrations. MCP doesn't remove the need for those services' own credentials; it only adds a conversational interface onto data the pipeline already writes to disk.
