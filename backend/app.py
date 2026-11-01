import logging
import os
import sys
from pathlib import Path

from flask import Flask, send_from_directory

sys.path.append(str(Path(__file__).resolve().parents[1]))

import config
from backend.data_store import store
from backend.api.routes import api

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)

store.bootstrap()
store.start_scheduler()

app = Flask(
    __name__,
    static_folder=str(config.FRONTEND_DIR),
    static_url_path=""
)

app.register_blueprint(api)


@app.get("/")
def index():
    return send_from_directory(config.FRONTEND_DIR, "index.html")


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/report")
def eda_report():
    if not config.EDA_REPORT_PATH.exists():
        return "EDA report not generated yet.", 404

    return send_from_directory(
        config.EDA_REPORT_PATH.parent,
        config.EDA_REPORT_PATH.name
    )


if __name__ == "__main__":
    app.run(
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", 5000)),
        debug=False
    )