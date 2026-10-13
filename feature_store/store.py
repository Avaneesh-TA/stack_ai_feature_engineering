"""
Local feature store API: a SQLite metadata/version registry (`feature_store/registry.db`,
table `feature_registry`) plus one parquet value snapshot per registered version
(`feature_store/values/<feature_name>__v<version>.parquet`).

Registry schema:
- feature_name: TEXT
- version: INTEGER
- created_at: TEXT (ISO-8601)
- description: TEXT
- source_columns: TEXT
- transform_summary: TEXT
- business_rationale: TEXT
- parameters: TEXT (JSON-encoded dict)
- parquet_path: TEXT
- is_latest: INTEGER (0/1)
Primary key: (feature_name, version)
"""

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import pandas as pd

REGISTRY_DB = "feature_store/registry.db"
VALUES_DIR = "feature_store/values"


def init_registry(db_path: str = REGISTRY_DB) -> None:
    """Initialize SQLite feature_registry table if it doesn't exist."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        with conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS feature_registry (
                    feature_name TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    description TEXT NOT NULL,
                    source_columns TEXT NOT NULL,
                    transform_summary TEXT NOT NULL,
                    business_rationale TEXT NOT NULL,
                    parameters TEXT NOT NULL,
                    parquet_path TEXT NOT NULL,
                    is_latest INTEGER NOT NULL,
                    PRIMARY KEY (feature_name, version)
                )
                """
            )
    finally:
        conn.close()


def register_version(
    feature_name: str,
    values_df: pd.DataFrame,
    description: str,
    source_columns: str,
    transform_summary: str,
    business_rationale: str,
    parameters: dict,
    db_path: str = REGISTRY_DB,
    values_dir: str = VALUES_DIR,
) -> int:
    """Write a new parquet snapshot, insert registry row, flip is_latest, return version number.

    Never overwrites an existing version's parquet snapshot or registry row.
    """
    init_registry(db_path)
    Path(values_dir).mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    try:
        with conn:
            # Query existing versions
            cur = conn.cursor()
            cur.execute(
                "SELECT COALESCE(MAX(version), 0) FROM feature_registry WHERE feature_name = ?",
                (feature_name,),
            )
            max_ver = cur.fetchone()[0]
            new_version = max_ver + 1

            # Format parquet path
            parquet_filename = f"{feature_name}__v{new_version}.parquet"
            parquet_path = f"{values_dir}/{parquet_filename}".replace("\\", "/")

            # Ensure snapshot file does not exist
            target_file = Path(parquet_path)
            if target_file.exists():
                raise FileExistsError(f"Parquet file already exists for version {new_version}: {parquet_path}")

            # Ensure snapshot has required columns: customer_id, <feature_name>, as_of_date
            # values_df may contain customer_id, feature column, and as_of_date
            cols_to_write = ["customer_id", feature_name, "as_of_date"]
            for col in cols_to_write:
                if col not in values_df.columns:
                    raise ValueError(f"values_df is missing required column: {col}")

            snapshot_df = values_df[cols_to_write].copy()
            snapshot_df.to_parquet(target_file, index=False)

            # Atomically flip prior is_latest to 0
            cur.execute(
                "UPDATE feature_registry SET is_latest = 0 WHERE feature_name = ?",
                (feature_name,),
            )

            # Insert new registry row with is_latest = 1
            created_at = datetime.now(timezone.utc).isoformat()
            cur.execute(
                """
                INSERT INTO feature_registry (
                    feature_name, version, created_at, description,
                    source_columns, transform_summary, business_rationale,
                    parameters, parquet_path, is_latest
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    feature_name,
                    new_version,
                    created_at,
                    description,
                    source_columns,
                    transform_summary,
                    business_rationale,
                    json.dumps(parameters),
                    parquet_path,
                ),
            )
            return new_version
    finally:
        conn.close()


def get_latest(feature_name: str, db_path: str = REGISTRY_DB) -> pd.DataFrame:
    """Return DataFrame for the version currently flagged is_latest = 1."""
    init_registry(db_path)
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT parquet_path FROM feature_registry WHERE feature_name = ? AND is_latest = 1",
            (feature_name,),
        )
        row = cur.fetchone()
        if not row:
            raise KeyError(f"Feature '{feature_name}' has no latest version registered in {db_path}")
        parquet_path = row[0]
        return pd.read_parquet(parquet_path)
    finally:
        conn.close()


def get_version(feature_name: str, version: int, db_path: str = REGISTRY_DB) -> pd.DataFrame:
    """Return DataFrame for a specific (feature_name, version)."""
    init_registry(db_path)
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT parquet_path FROM feature_registry WHERE feature_name = ? AND version = ?",
            (feature_name, version),
        )
        row = cur.fetchone()
        if not row:
            raise KeyError(f"Feature '{feature_name}' version {version} not found in {db_path}")
        parquet_path = row[0]
        return pd.read_parquet(parquet_path)
    finally:
        conn.close()


def list_versions(feature_name: str, db_path: str = REGISTRY_DB) -> pd.DataFrame:
    """Return every registered version's metadata row for feature_name, most recent first."""
    init_registry(db_path)
    conn = sqlite3.connect(db_path)
    try:
        df = pd.read_sql(
            "SELECT * FROM feature_registry WHERE feature_name = ? ORDER BY version DESC",
            conn,
            params=(feature_name,),
        )
        return df
    finally:
        conn.close()
