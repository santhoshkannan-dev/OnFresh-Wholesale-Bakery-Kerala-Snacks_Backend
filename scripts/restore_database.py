"""
OnFresh Safe PostgreSQL Database Restoration Utility.
Restores a compressed .sql.gz backup to a target database with integrity checks.
Requires explicit confirmation to prevent accidental production overwrite.
"""

import os
import sys
import gzip
import hashlib
import subprocess
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')

BACKUP_DIR = BASE_DIR / 'backups' / 'database'

DB_NAME = os.getenv('DB_NAME', 'onfresh_db')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'santhosh')
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '5432')


def compute_sha256(filepath: Path) -> str:
    sha256 = hashlib.sha256()
    with open(filepath, 'rb') as f:
        while chunk := f.read(65536):
            sha256.update(chunk)
    return sha256.hexdigest()


def restore_backup(backup_file: str, force: bool = False):
    backup_path = Path(backup_file)
    if not backup_path.is_absolute():
        backup_path = BACKUP_DIR / backup_file

    if not backup_path.exists():
        print(f"ERROR: Backup file '{backup_path}' does not exist.", file=sys.stderr)
        sys.exit(1)

    # Check for SHA256 file
    checksum_file = backup_path.parent / f"{backup_path.name}.sha256"
    if checksum_file.exists():
        expected_hash = checksum_file.read_text().split()[0].strip()
        actual_hash = compute_sha256(backup_path)
        if expected_hash.lower() != actual_hash.lower():
            print(f"CRITICAL ERROR: SHA-256 checksum mismatch!\nExpected: {expected_hash}\nActual:   {actual_hash}", file=sys.stderr)
            sys.exit(1)
        print("✓ SHA-256 Checksum verified successfully.")

    print("=" * 60)
    print("ONFRESH DATABASE RESTORATION")
    print(f"Target Database : {DB_NAME}")
    print(f"Target Host     : {DB_HOST}:{DB_PORT}")
    print(f"Target User     : {DB_USER}")
    print(f"Source Backup   : {backup_path.name}")
    print("=" * 60)

    if not force:
        confirm = input(f"WARNING: This will restore to '{DB_NAME}'. Type 'CONFIRM-RESTORE' to proceed: ")
        if confirm.strip() != 'CONFIRM-RESTORE':
            print("Restoration cancelled.")
            sys.exit(0)

    print(f"Restoring {backup_path} into {DB_NAME}...")

    env = os.environ.copy()
    if DB_PASSWORD:
        env['PGPASSWORD'] = DB_PASSWORD

    cmd = [
        'psql',
        '-h', DB_HOST,
        '-p', str(DB_PORT),
        '-U', DB_USER,
        '-d', DB_NAME,
    ]

    try:
        with gzip.open(backup_path, 'rb') as gz_in:
            process = subprocess.Popen(
                cmd,
                stdin=gz_in,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env
            )
            stdout, stderr = process.communicate()

            if process.returncode != 0:
                err_msg = stderr.decode('utf-8', errors='replace')
                print(f"ERROR: psql restoration failed (Code {process.returncode}):\n{err_msg}", file=sys.stderr)
                sys.exit(1)

        print(f"SUCCESS: Database '{DB_NAME}' successfully restored from {backup_path.name}.")
    except FileNotFoundError:
        print("ERROR: 'psql' utility not found on PATH.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR during restore execution: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python restore_database.py <backup_filename_or_path> [--force]")
        sys.exit(1)

    file_arg = sys.argv[1]
    is_force = '--force' in sys.argv
    restore_backup(file_arg, force=is_force)

