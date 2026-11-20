from __future__ import annotations

import os

import uvicorn

from localtv.server import app


def main() -> None:
    host = os.environ.get("LOCALTV_HOST", "127.0.0.1")
    port = int(os.environ.get("LOCALTV_PORT", "8787"))
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
