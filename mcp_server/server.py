"""
mcp_server/server.py — read-only MCP server over the dashboard's run history.

Exposes storage.run_store's list_runs/load_run/compute_stats as MCP tools so
Claude Desktop/Code can answer questions about past pipeline runs directly
("what was my best match this week?") without touching main.py or any of the
pipeline's scraping/scoring/optimizing/email integrations. Runs locally over
stdio, reading the same data/runs/*.json files the webapp dashboard reads —
no new credentials, no hosting cost.
"""

from mcp.server.fastmcp import FastMCP

from storage import run_store

mcp = FastMCP("job-search-history")


@mcp.tool()
def list_runs() -> list[dict]:
    """List every pipeline run (summary only, no per-job detail), newest first.

    Each entry has: run_id, started_at, finished_at, dry_run, email_sent,
    total_scraped, total_scored, total_qualifying, source
    (cli/github_actions/webapp), github_run_url, error_count.
    """
    return run_store.list_runs()


@mcp.tool()
def load_run(run_id: str) -> dict | None:
    """Load one run's full snapshot, including every scored job (qualifying
    or not) with fields like title, company, match_score, matched_keywords,
    recommendation. Get run_id from list_runs(). Returns None if not found.
    """
    return run_store.load_run(run_id)


@mcp.tool()
def compute_stats() -> dict:
    """Aggregate stats across all runs: total_runs, total_jobs_scraped,
    total_jobs_qualifying, runs_over_time, score_distribution,
    source_breakdown, and top_companies (by qualifying match count).
    """
    return run_store.compute_stats()
