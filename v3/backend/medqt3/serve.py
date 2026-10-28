"""Run the API alone (development: the UI runs on Vite and proxies /api here)."""

import uvicorn

from .api import create_app

if __name__ == "__main__":
    uvicorn.run(create_app(), host="127.0.0.1", port=8765)
