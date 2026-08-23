import os
import uvicorn

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    uvicorn.run("webapp.app:app", host="127.0.0.1", port=port, reload=True)
