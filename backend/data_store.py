import json
import logging
import sqlite3
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.append(str(Path(__file__).resolve().parents[1]))

import config
from etl import etl_pipeline

log = logging.getLogger("aq.store")

RETRY_AFTER_FAILURE_SECONDS = 300
SCHEDULER_TICK_SECONDS = 30


class DataStore:
    def __init__(self):
        self._lock = threading.Lock()
        self._eda_lock = threading.Lock()
        self.df: pd.DataFrame | None = None
        self.etl_report: dict = {}
        self.columns: list[str] = []
        self.refreshing = False
        self.last_attempt = 0.0
        self.last_error: str | None = None
        self.last_duration: float | None = None
        self.scheduler_started = False

    def load(self) -> None:
        with sqlite3.connect(config.DB_PATH) as conn:
            df = pd.read_sql_query(
                f"SELECT * FROM {config.DB_TABLE}",
                conn,
                parse_dates=["timestamp", "date"]
            )

        report = json.loads(
            config.ETL_REPORT_PATH.read_text(encoding="utf-8")
        )

        self.columns = list(df.columns)
        self.etl_report = report
        self.df = df

        log.info(
            "Loaded %s rows (%s -> %s)",
            f"{len(df):,}",
            df["timestamp"].min(),
            df["timestamp"].max()
        )

    def bootstrap(self) -> None:
        self._load_or_build()
        self.start_scheduler()

    def _load_or_build(self) -> None:
        if config.DB_PATH.exists() and config.ETL_REPORT_PATH.exists():
            self.load()
            self.last_attempt = config.DB_PATH.stat().st_mtime
            return

        log.info("No processed data yet - building it from the API")
        self.refresh_blocking()

        if self.df is not None:
            return

        if config.RAW_PATH.exists():
            log.warning(
                "API unavailable (%s) - falling back to the bundled CSV",
                self.last_error
            )
            etl_pipeline.run("csv", config.RAW_PATH)
            self.load()
            self.last_attempt = time.time()
            return

        raise RuntimeError(
            f"Could not build the dataset from the API ({self.last_error}) "
            "and no CSV fallback exists."
        )

    def _claim(self) -> bool:
        with self._lock:
            if self.refreshing:
                return False

            self.refreshing = True
            self.last_attempt = time.time()
            return True

    def _do_refresh(self) -> None:
        started = time.time()
        succeeded = False

        try:
            etl_pipeline.run("api")
            self.load()
            self.last_error = None
            succeeded = True

        except ConnectionError as exc:
            self.last_error = f"ConnectionError: {exc}"
            log.warning(
                "Refresh skipped - API unreachable, still serving the previous data (%s)",
                str(exc)[:200]
            )

        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            log.exception(
                "Refresh failed - still serving the previous data"
            )

        finally:
            self.last_duration = round(time.time() - started, 1)
            self.refreshing = False

        if succeeded:
            log.info(
                "Refresh finished in %.1fs",
                self.last_duration
            )

            threading.Thread(
                target=self._rebuild_eda_report,
                name="aq-eda",
                daemon=True
            ).start()

    def _rebuild_eda_report(self) -> None:
        if not self._eda_lock.acquire(blocking=False):
            return

        try:
            from eda import exploratory_analysis
            exploratory_analysis.main()

        except Exception:
            log.exception("Could not rebuild the static EDA report")

        finally:
            self._eda_lock.release()

    def start_refresh(self) -> bool:
        if not self._claim():
            return False

        threading.Thread(
            target=self._do_refresh,
            name="aq-refresh",
            daemon=True
        ).start()

        return True

    def refresh_blocking(self) -> bool:
        if not self._claim():
            return False

        self._do_refresh()
        return True

    def maybe_refresh(self) -> None:
        wait = (
            RETRY_AFTER_FAILURE_SECONDS
            if self.last_error
            else config.REFRESH_MINUTES * 60
        )

        if (
            not self.refreshing
            and time.time() - self.last_attempt >= wait
        ):
            self.start_refresh()

    def _scheduler_loop(self) -> None:
        while True:
            try:
                self.maybe_refresh()
            except Exception:
                log.exception("Automatic refresh scheduler error")

            time.sleep(SCHEDULER_TICK_SECONDS)

    def start_scheduler(self) -> None:
        with self._lock:
            if self.scheduler_started:
                return

            self.scheduler_started = True

        threading.Thread(
            target=self._scheduler_loop,
            name="aq-scheduler",
            daemon=True
        ).start()

        log.info(
            "Automatic refresh scheduler started: every %s minutes",
            config.REFRESH_MINUTES
        )

    def status(self) -> dict:
        extract = self.etl_report.get("extract", {})

        return {
            "last_refresh": self.etl_report.get("generated_at"),
            "mode": extract.get("mode", "csv"),
            "source": extract.get("source"),
            "rows": 0 if self.df is None else int(len(self.df)),
            "latest_record": (
                None
                if self.df is None
                else self.df["timestamp"].max().strftime("%Y-%m-%d %H:%M")
            ),
            "refreshing": self.refreshing,
            "last_error": self.last_error,
            "last_duration_seconds": self.last_duration,
            "refresh_minutes": config.REFRESH_MINUTES,
            "server_time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "seconds_since_attempt": round(time.time() - self.last_attempt),
        }


store = DataStore()