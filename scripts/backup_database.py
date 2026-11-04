"""
OnFresh Automated PostgreSQL Database Backup Utility.
Designed for Linux/Unix and Windows production environments.
Executes compressed pg_dump, generates SHA-256 integrity checksums,
and applies retention pruning (default: 30 days).
"""

import os
import sys
import gzip
import shutil
import hashlib
import datetime
import subprocess
from pathlib import Path
from dotenv import load_dotenv

# Base paths
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')

BACKUP_DIR = BASE_DIR / 'backups' / 'database'
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

# Database credentials
DB_NAME = os.getenv('DB_NAME', 'onfresh_db')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'santhosh')
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '5432')
RETENTION_DAYS = int(os.getenv('BACKUP_RETENTION_DAYS', '30'))


def compute_sha256(filepath: Path) -> str:
    sha256 = hashlib.sha256()
    with open(filepath, 'rb') as f:
        while chunk := f.read(65536):
            sha256.update(chunk)
    return sha256.hexdigest()


def run_backup():
    now_str = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_filename = f"onfresh_{DB_NAME}_{now_str}.sql.gz"
    backup_path = BACKUP_DIR / backup_filename
    checksum_path = BACKUP_DIR / f"{backup_filename}.sha256"

    print(f"[{datetime.datetime.now()}] Initiating backup of database '{DB_NAME}' on {DB_HOST}:{DB_PORT}...")

    # Set password in environment for pg_dump
    env = os.environ.copy()
    if DB_PASSWORD:
        env['PGPASSWORD'] = DB_PASSWORD

    cmd = [
        'pg_dump',
        '-h', DB_HOST,
        '-p', str(DB_PORT),
        '-U', DB_USER,
        '-d', DB_NAME,
        '--no-owner',
        '--no-privileges',
    ]

    try:
        # Run pg_dump streaming through gzip
        with gzip.open(backup_path, 'wb') as gz_out:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env
            )
            stdout, stderr = process.communicate()

            if process.returncode != 0:
                err_msg = stderr.decode('utf-8', errors='replace')
                print(f"ERROR: pg_dump failed with return code {process.returncode}:\n{err_msg}", file=sys.stderr)
                if backup_path.exists():
                    backup_path.unlink()
                sys.exit(1)

            gz_out.write(stdout)

        # Compute and write SHA-256
        checksum = compute_sha256(backup_path)
        with open(checksum_path, 'w', encoding='utf-8') as f:
            f.write(f"{checksum}  {backup_filename}\n")

        file_size_mb = backup_path.stat().st_size / (1024 * 1024)
        print(f"SUCCESS: Database backup written to {backup_path} ({file_size_mb:.2f} MB)")
        print(f"SHA-256 Checksum: {checksum}")

        # Retention pruning
        prune_old_backups(RETENTION_DAYS)

    except FileNotFoundError:
        print(
            "ERROR: 'pg_dump' utility not found on PATH. Ensure PostgreSQL client tools are installed and in system PATH.",
            file=sys.stderr
        )
        sys.exit(1)
    except Exception as e:
        print(f"ERROR during backup execution: {e}", file=sys.stderr)
        sys.exit(1)


def prune_old_backups(days: int):
    cutoff = datetime.datetime.now() - datetime.timedelta(days=days)
    pruned_count = 0

    for file in BACKUP_DIR.glob('onfresh_*.sql.gz*'):
        mtime = datetime.datetime.fromtimestamp(file.stat().st_mtime)
        if mtime < cutoff:
            file.unlink()
            pruned_count += 1

    if pruned_count > 0:
        print(f"Pruned {pruned_count} backup files older than {days} days.")


if __name__ == '__main__':
    run_backup()

