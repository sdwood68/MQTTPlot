"""Operational CLI for MQTTPlot."""
from __future__ import annotations

import argparse
import getpass
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from werkzeug.security import generate_password_hash
import requests

from version import __version__

DEFAULT_SECRET_FILE = "/opt/mqttplot/secret.env"
DEFAULT_BACKUP_KEEP = 10


def _load_runtime_env() -> None:
    secret_file = os.environ.get("MQTTPLOT_SECRET_FILE", DEFAULT_SECRET_FILE)
    if os.path.exists(secret_file):
        load_dotenv(secret_file, override=False)


_load_runtime_env()

from . import config
from .mqtt_client import get_status as get_mqtt_status


def _iso(ts: float | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).replace(microsecond=0).isoformat()


def _systemctl_state() -> dict[str, Any]:
    systemctl = shutil.which("systemctl")
    if not systemctl:
        return {"available": False, "active": None, "enabled": None}

    def _run(*args: str) -> tuple[int, str]:
        proc = subprocess.run(
            [systemctl, *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
        return proc.returncode, proc.stdout.strip()

    active_rc, active_out = _run("is-active", "mqttplot")
    enabled_rc, enabled_out = _run("is-enabled", "mqttplot")
    return {
        "available": True,
        "active": active_rc == 0,
        "active_text": active_out,
        "enabled": enabled_rc == 0,
        "enabled_text": enabled_out,
    }


def _fetch_local_health() -> dict[str, Any] | None:
    url = f"http://127.0.0.1:{config.FLASK_PORT}/api/health"
    try:
        resp = requests.get(url, timeout=2)
        return {
            "reachable": True,
            "status_code": resp.status_code,
            "payload": resp.json(),
        }
    except Exception as exc:
        return {
            "reachable": False,
            "error": f"{type(exc).__name__}: {exc}",
            "url": url,
        }


def _db_file_stats(path: Path) -> dict[str, Any]:
    info: dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
        "size_bytes": path.stat().st_size if path.exists() else 0,
        "mtime_iso": _iso(path.stat().st_mtime) if path.exists() else None,
    }
    if not path.exists():
        return info

    try:
        con = sqlite3.connect(path)
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        info["tables"] = [r[0] for r in cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()]
        info["integrity_ok"] = (
            cur.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        )
        con.close()
    except Exception as exc:
        info["integrity_ok"] = False
        info["error"] = f"{type(exc).__name__}: {exc}"
    return info


def _aggregate_db_info() -> dict[str, Any]:
    meta_path = Path(config.DB_PATH)
    data_dir = Path(config.DATA_DB_DIR)
    data_files = sorted(data_dir.glob("*.db")) if data_dir.exists() else []

    info: dict[str, Any] = {
        "version": __version__,
        "metadata_db": _db_file_stats(meta_path),
        "data_db_dir": str(data_dir),
        "data_db_count": len(data_files),
        "data_db_total_size_bytes": sum(p.stat().st_size for p in data_files if p.exists()),
        "data_dbs": [],
    }

    for db_path in data_files:
        db_info = _db_file_stats(db_path)
        try:
            con = sqlite3.connect(db_path)
            cur = con.cursor()
            topic_count = cur.execute("SELECT COUNT(*) FROM topics").fetchone()[0]
            message_count = cur.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
            db_info["topic_count"] = int(topic_count)
            db_info["message_count"] = int(message_count)
            con.close()
        except Exception as exc:
            db_info["error"] = f"{type(exc).__name__}: {exc}"
        info["data_dbs"].append(db_info)

    if meta_path.exists():
        try:
            con = sqlite3.connect(meta_path)
            con.row_factory = sqlite3.Row
            cur = con.cursor()
            info["admin_user_count"] = int(cur.execute(
                "SELECT COUNT(*) FROM admin_users"
            ).fetchone()[0])
            info["tracked_topic_count"] = int(cur.execute(
                "SELECT COUNT(*) FROM topic_stats"
            ).fetchone()[0])
            info["public_plot_count"] = int(cur.execute(
                "SELECT COUNT(*) FROM public_plots"
            ).fetchone()[0])
            info["top_topics"] = [
                {
                    "topic": row["topic"],
                    "message_count": int(row["message_count"] or 0),
                    "last_seen_ts_epoch": row["last_seen_ts_epoch"],
                }
                for row in cur.execute(
                    """
                    SELECT topic, message_count, last_seen_ts_epoch
                    FROM topic_stats
                    ORDER BY message_count DESC, topic ASC
                    LIMIT 10
                    """
                ).fetchall()
            ]
            con.close()
        except Exception as exc:
            info["metadata_error"] = f"{type(exc).__name__}: {exc}"

    return info


def cmd_status(_args: argparse.Namespace) -> int:
    status = {
        "version": __version__,
        "hostname": socket.gethostname(),
        "metadata_db": config.DB_PATH,
        "data_db_dir": config.DATA_DB_DIR,
        "mqtt_broker": config.MQTT_BROKER,
        "mqtt_port": config.MQTT_PORT,
        "mqtt_topics": config.MQTT_TOPICS,
        "systemd": _systemctl_state(),
        "health_api": _fetch_local_health(),
        "mqtt_runtime": get_mqtt_status(),
        "db_summary": {
            "metadata_exists": os.path.exists(config.DB_PATH),
            "data_db_count": len(list(Path(config.DATA_DB_DIR).glob("*.db")))
            if os.path.isdir(config.DATA_DB_DIR)
            else 0,
        },
    }
    print(json.dumps(status, indent=2, sort_keys=True))
    return 0


def cmd_db_info(args: argparse.Namespace) -> int:
    info = _aggregate_db_info()
    if args.json:
        print(json.dumps(info, indent=2, sort_keys=True))
        return 0

    print(f"MQTTPlot {info['version']}")
    print(f"Metadata DB: {info['metadata_db']['path']}")
    print(f"Data DB dir: {info['data_db_dir']}")
    print(f"Data DB count: {info['data_db_count']}")
    print(f"Data DB total size: {info['data_db_total_size_bytes']} bytes")
    if 'admin_user_count' in info:
        print(f"Admin users: {info['admin_user_count']}")
    if 'tracked_topic_count' in info:
        print(f"Tracked topics: {info['tracked_topic_count']}")
    if 'public_plot_count' in info:
        print(f"Public plots: {info['public_plot_count']}")
    if info.get("top_topics"):
        print("Top topics:")
        for row in info["top_topics"]:
            print(f"  - {row['topic']}: {row['message_count']} messages")
    return 0


def _ensure_backup_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _sqlite_backup(src: Path, dest: Path) -> None:
    src_con = sqlite3.connect(src)
    try:
        dest_con = sqlite3.connect(dest)
        try:
            src_con.backup(dest_con)
        finally:
            dest_con.close()
    finally:
        src_con.close()


def _rotate_backups(backup_dir: Path, keep: int) -> list[str]:
    if keep <= 0:
        return []
    archives = sorted(
        backup_dir.glob("mqttplot-backup-*.tar.gz"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    removed: list[str] = []
    for old in archives[keep:]:
        old.unlink(missing_ok=True)
        removed.append(str(old))
    return removed


def cmd_backup(args: argparse.Namespace) -> int:
    backup_dir = Path(args.output_dir or os.environ.get("MQTTPLOT_BACKUP_DIR") or "/opt/mqttplot/backups")
    keep = args.keep if args.keep is not None else int(os.environ.get("MQTTPLOT_BACKUP_KEEP", DEFAULT_BACKUP_KEEP))
    _ensure_backup_dir(backup_dir)

    ts = datetime.now(tz=timezone.utc).strftime("%Y%m%d-%H%M%S")
    archive_path = backup_dir / f"mqttplot-backup-{ts}.tar.gz"

    with tempfile.TemporaryDirectory(prefix="mqttplot-backup-") as tmpdir:
        stage = Path(tmpdir)
        snapshot_dir = stage / "snapshot"
        snapshot_dir.mkdir(parents=True, exist_ok=True)

        manifest = {
            "version": __version__,
            "created_utc": datetime.now(tz=timezone.utc).replace(microsecond=0).isoformat(),
            "metadata_db": str(config.DB_PATH),
            "data_db_dir": str(config.DATA_DB_DIR),
            "hostname": socket.gethostname(),
        }

        meta_src = Path(config.DB_PATH)
        if meta_src.exists():
            _sqlite_backup(meta_src, snapshot_dir / meta_src.name)

        data_src_dir = Path(config.DATA_DB_DIR)
        data_snapshot_dir = snapshot_dir / "data"
        data_snapshot_dir.mkdir(parents=True, exist_ok=True)
        if data_src_dir.exists():
            for db_file in sorted(data_src_dir.glob("*.db")):
                _sqlite_backup(db_file, data_snapshot_dir / db_file.name)

        (snapshot_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        with tarfile.open(archive_path, "w:gz") as tar:
            tar.add(snapshot_dir, arcname="mqttplot-backup")

    removed = _rotate_backups(backup_dir, keep)
    result = {
        "archive": str(archive_path),
        "keep": keep,
        "removed": removed,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def cmd_reset_admin_password(args: argparse.Namespace) -> int:
    username = args.username
    password = args.password

    if not password:
        password = getpass.getpass(f"New password for {username}: ")
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            print("Passwords do not match.", file=sys.stderr)
            return 1

    if not password:
        print("Password cannot be empty.", file=sys.stderr)
        return 1

    db_path = Path(config.DB_PATH)
    if not db_path.exists():
        print(f"Metadata database not found: {db_path}", file=sys.stderr)
        return 1

    con = sqlite3.connect(db_path)
    try:
        cur = con.cursor()
        cur.execute("SELECT 1 FROM admin_users WHERE username=?", (username,))
        exists = cur.fetchone() is not None
        password_hash = generate_password_hash(password)
        now = time.time()
        if exists:
            cur.execute(
                "UPDATE admin_users SET password_hash=? WHERE username=?",
                (password_hash, username),
            )
        else:
            cur.execute(
                """
                INSERT INTO admin_users(username, password_hash, created_ts_epoch)
                VALUES(?, ?, ?)
                """,
                (username, password_hash, now),
            )
        con.commit()
    finally:
        con.close()

    print(json.dumps({"status": "ok", "username": username}, indent=2))
    return 0


def cmd_reload(_args: argparse.Namespace) -> int:
    systemctl = shutil.which("systemctl")
    if not systemctl:
        print("systemctl not available on this host", file=sys.stderr)
        return 1
    proc = subprocess.run(
        [systemctl, "restart", "mqttplot"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        sys.stderr.write(proc.stdout)
        return proc.returncode
    print(json.dumps({"status": "ok", "action": "restart", "service": "mqttplot"}, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mqttplot", description="MQTTPlot operational CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("status", help="Show service/runtime status")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("db-info", help="Inspect metadata and per-root SQLite databases")
    p.add_argument("--json", action="store_true", help="Emit JSON instead of human-readable text")
    p.set_defaults(func=cmd_db_info)

    p = sub.add_parser("backup", help="Create a timestamped database backup archive")
    p.add_argument("--output-dir", help="Directory for backup archives")
    p.add_argument("--keep", type=int, help="How many backup archives to retain after rotation")
    p.set_defaults(func=cmd_backup)

    p = sub.add_parser("reset-admin-password", help="Reset or create an admin password")
    p.add_argument("--username", default="admin", help="Admin username (default: admin)")
    p.add_argument("--password", help="Password to set; omit to be prompted securely")
    p.set_defaults(func=cmd_reset_admin_password)

    p = sub.add_parser("reload", help="Restart the mqttplot service to reload secret.env")
    p.set_defaults(func=cmd_reload)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
