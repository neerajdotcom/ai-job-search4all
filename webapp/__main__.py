"""`python -m webapp` entrypoint — runs the dashboard on 127.0.0.1 only."""

import uvicorn

if __name__ == "__main__":
    uvicorn.run("webapp.app:app", host="127.0.0.1", port=8000, reload=False)
