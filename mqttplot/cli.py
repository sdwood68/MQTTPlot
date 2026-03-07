
"""Operational CLI for MQTTPlot."""
from __future__ import annotations

import argparse
import getpass
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from werkzeug.security import generate_password_hash

DEFAULT_SECRET_FILE = os.environ.get("MQTTPLOT_SECRET_FILE", "/opt/mqttplot/secret.env")


def _load_runtime_env() -> None:
    secret_file = os.environ.get("MQTTPLOT_SECRET_FILE", DEFAULT_SECRET_FILE)
    if secret_file and os.path.exists(secret_file):
        load_dotenv(secret_file, override=False)


_load_runtime_env()

from mqttplot import config  # noqa: E402
from mqttplot.storage import init_meta_db, record_app_version  # noqa: E402
from version import __version__  # noqa: E402


def _meta_db_path() -> Path:
    return Path(config.DB_PATH)


def _data_db_dir() -> Path:
    return Path(config.DATA_DB_DIR)


def _run_systemctl(*args: str) -> int:
    return subprocess.call(["systemctl", *args])


def cmd_status(_args: argparse.Namespace) -> int:
    rc = _run_systemctl("--no-pager", "--full", "status", "mqttplot")
    return 0 if rc == 0 else rc


def cmd_reload(_args: argparse.Namespace) -> int:
    rc = _run_systemctl("restart", "mqttplot")
    if rc == 0:
        print("mqttplot service restarted.")
    return rc


def cmd_reset_admin_password(args: argparse.Namespace) -> int:
    password = args.password
    if not password:
        pw1 = getpass.getpass("New admin password: ")
        pw2 = getpass.getpass("Confirm admin password: ")
        if pw1 != pw2:
            print("Passwords do not match.", file=sys.stderr)
            return 2
        password = pw1
    if not password:
        print("Password cannot be empty.", file=sys.stderr)
        return 2

    init_meta_db()
    conn = sqlite3.connect(str(_meta_db_path()))
    try:
        conn.execute(
            """
            INSERT INTO admin_users(username, password_hash, created_ts_epoch)
            VALUES(?, ?, ?)
            ON CONFLICT(username) DO UPDATE SET password_hash=excluded.password_hash
            """,
            ("admin", generate_password_hash(password), time.time()),
        )
        conn.commit()
    finally:
        conn.close()

    print("Admin password updated for user 'admin'.")
    return 0


def _format_bytes(n: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(n)
    for unit in units:
        if value < 1024.0 or unit == units[-1]:
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} {unit}"
        value /= 1024.0
    return f"{n} B"


def cmd_db_info(_args: argparse.Namespace) -> int:
    meta = _meta_db_path()
    data_dir = _data_db_dir()
    print(f"Version: {__version__}")
    print(f"Metadata DB: {meta}")
    if meta.exists():
        print(f"  Size: {_format_bytes(meta.stat().st_size)}")
    else:
        print("  Missing")

    print(f"Data DB dir: {data_dir}")
    if data_dir.exists():
        dbs = sorted(data_dir.glob("*.db"))
        total = sum(p.stat().st_size for p in dbs)
        print(f"  Files: {len(dbs)}")
        print(f"  Total size: {_format_bytes(total)}")
        for p in dbs:
            print(f"   - {p.name}: {_format_bytes(p.stat().st_size)}")
    else:
        print("  Missing")
    return 0


def cmd_backup(args: argparse.Namespace) -> int:
    src_meta = _meta_db_path()
    src_data = _data_db_dir()
    backup_root = Path(args.output or "/opt/mqttplot/backups")
    backup_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    dest = backup_root / f"mqttplot-backup-{stamp}"
    dest.mkdir(parents=True, exist_ok=True)

    if src_meta.exists():
        shutil.copy2(src_meta, dest / src_meta.name)
    if src_data.exists():
        shutil.copytree(src_data, dest / src_data.name, dirs_exist_ok=True)

    archive = shutil.make_archive(str(dest), "zip", root_dir=str(dest))
    shutil.rmtree(dest, ignore_errors=True)
    print(f"Created backup: {archive}")

    keep = max(1, int(args.keep))
    archives = sorted(backup_root.glob("mqttplot-backup-*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in archives[keep:]:
        old.unlink(missing_ok=True)
    print(f"Retained {min(len(archives), keep)} backup archive(s).")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mqttplot", description="MQTTPlot operational CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("status", help="Show systemd service status")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("reload", help="Restart mqttplot so it reloads secret.env")
    p.set_defaults(func=cmd_reload)

    p = sub.add_parser("reset-admin-password", help="Reset the admin password")
    p.add_argument("--password", help="Password to set non-interactively")
    p.set_defaults(func=cmd_reset_admin_password)

    p = sub.add_parser("db-info", help="Show metadata/data DB locations and sizes")
    p.set_defaults(func=cmd_db_info)

    p = sub.add_parser("backup", help="Create a ZIP backup of the metadata and data DBs")
    p.add_argument("--output", help="Backup directory", default="/opt/mqttplot/backups")
    p.add_argument("--keep", type=int, default=5, help="How many ZIP backups to retain")
    p.set_defaults(func=cmd_backup)

    return parser


def main(argv: list[str] | None = None) -> int:
    init_meta_db()
    record_app_version(__version__)
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
