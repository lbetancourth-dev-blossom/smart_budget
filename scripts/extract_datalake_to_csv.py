"""
Extract tables from the Blossom Analytics Datalake (S3) to CSV files.

Supports any source (DOUGH, OLB, SAFE, ...) across any layer (bronze, silver, gold).

Usage examples:

  # List all available sources in the datalake
  python3 extract_datalake_to_csv.py --list

  # Extract all tables from all sources (silver layer, dev env)
  python3 extract_datalake_to_csv.py

  # Extract only DOUGH tables, both layers
  python3 extract_datalake_to_csv.py --source DOUGH --layer all

  # Extract only OLB silver
  python3 extract_datalake_to_csv.py --source OLB --layer silver

  # Extract a single table
  python3 extract_datalake_to_csv.py --source DOUGH --layer silver --table externaltransaction

  # Alpha environment
  python3 extract_datalake_to_csv.py --source SAFE --env alpha

  # More parallel workers for partitioned tables (e.g. OLB)
  python3 extract_datalake_to_csv.py --source OLB --workers 40
"""

import argparse
import io
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import boto3
import pandas as pd
import pyarrow.parquet as pq

# ── Config ────────────────────────────────────────────────────────────────────

BUCKETS = {
    "dev": "blossom-analytics-datalake-dev",
    "alpha": "blossom-analytics-datalake-alpha",
}
LAYERS = ["bronze", "silver", "gold"]
PROFILE = "blossom-dev"

SKIP_TABLES = {
    "_bronze_watermark",
    "_silver_watermark",
    "_gold_watermark",
    "logs",
    "migrations",
    "seeder_tracking",
}

ROOT = Path(__file__).parent.parent  # repo root


# ── AWS ───────────────────────────────────────────────────────────────────────


def get_s3_client():
    session = boto3.Session(profile_name=PROFILE)
    return session.client("s3")


# ── Discovery ─────────────────────────────────────────────────────────────────


def list_sources(s3, bucket, layer):
    """Return list of source names (DOUGH, OLB, SAFE, ...) in a given layer."""
    prefix = f"datalake/{layer}/"
    resp = s3.list_objects_v2(Bucket=bucket, Prefix=prefix, Delimiter="/")
    return [cp["Prefix"].split("/")[-2] for cp in resp.get("CommonPrefixes", [])]


def list_tables(s3, bucket, source_prefix):
    """Return table names under a source prefix."""
    resp = s3.list_objects_v2(Bucket=bucket, Prefix=source_prefix, Delimiter="/")
    return [
        cp["Prefix"].split("/")[-2]
        for cp in resp.get("CommonPrefixes", [])
        if cp["Prefix"].split("/")[-2] not in SKIP_TABLES
    ]


def list_parquet_files(s3, bucket, prefix):
    """Return all .parquet keys under prefix (handles pagination)."""
    files = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            if obj["Key"].endswith(".parquet"):
                files.append(obj["Key"])
    return files


# ── Reading ───────────────────────────────────────────────────────────────────


def _read_one(s3, bucket, key):
    """Read a single parquet file from S3 → DataFrame."""
    resp = s3.get_object(Bucket=bucket, Key=key)
    buf = io.BytesIO(resp["Body"].read())
    return pq.read_table(buf).to_pandas()


def read_parquet_files(s3, bucket, keys, workers=20):
    """Read multiple parquet files in parallel → concatenated DataFrame."""
    if not keys:
        return None

    dfs = []
    errors = 0

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_read_one, s3, bucket, k): k for k in keys}
        for fut in as_completed(futures):
            key = futures[fut]
            try:
                dfs.append(fut.result())
            except Exception as e:
                errors += 1
                print(f"\n  ⚠️  Error reading {key}: {e}")

    if errors:
        print(f"  ⚠️  {errors} file(s) failed to read")
    if not dfs:
        return None

    df = pd.concat(dfs, ignore_index=True)
    return df.drop_duplicates()


# ── Extraction ────────────────────────────────────────────────────────────────


def extract_table(s3, bucket, layer, source, table, output_dir, workers):
    """Extract a single table → CSV. Returns row count or None."""
    table_prefix = f"datalake/{layer}/{source}/{table}/data/"
    parquet_files = list_parquet_files(s3, bucket, table_prefix)

    if not parquet_files:
        # Some tables store data directly (no /data/ sub-path)
        table_prefix_alt = f"datalake/{layer}/{source}/{table}/"
        parquet_files = [
            k
            for k in list_parquet_files(s3, bucket, table_prefix_alt)
            if "/data/" not in k or True  # include all
        ]

    if not parquet_files:
        return None, 0

    df = read_parquet_files(s3, bucket, parquet_files, workers=workers)
    if df is None or df.empty:
        return None, 0

    out_path = output_dir / f"{table}.csv"
    output_dir.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False, encoding="utf-8-sig")
    return out_path, len(df)


def extract_source(s3, bucket, env, layer, source, tables_filter, workers):
    """Extract all tables (or filtered subset) for one source+layer."""
    source_prefix = f"datalake/{layer}/{source}/"
    all_tables = list_tables(s3, bucket, source_prefix)

    if not all_tables:
        print(f"  [NO TABLES FOUND at {source_prefix}]")
        return

    if tables_filter:
        tables = [
            t for t in all_tables if t.lower() in {t.lower() for t in tables_filter}
        ]
        missing = set(tables_filter) - {t.lower() for t in all_tables}
        if missing:
            print(f"  ⚠️  Tables not found: {missing}")
    else:
        tables = all_tables

    output_dir = ROOT / "data" / source.lower() / env / layer

    print(f"\n{'='*60}")
    print(f"  {source} / {layer.upper()} — {len(tables)} table(s)")
    print(f"  Output: {output_dir}")
    print(f"{'='*60}")

    total_rows = 0
    for table in sorted(tables):
        print(f"  → {table}", end="", flush=True)
        out_path, rows = extract_table(
            s3, bucket, layer, source, table, output_dir, workers
        )
        if out_path is None:
            print("  [NO DATA]")
        else:
            print(f"  ✓  {rows:,} rows  →  {table}.csv")
            total_rows += rows

    print(f"\n  ✅ {source}/{layer}: {total_rows:,} total rows saved")


# ── List mode ─────────────────────────────────────────────────────────────────


def cmd_list(s3, bucket, layers):
    """Print all available sources and their tables."""
    print(f"\nDatalake: {bucket}\n")
    for layer in layers:
        sources = list_sources(s3, bucket, layer)
        if not sources:
            continue
        print(f"  [{layer.upper()}]")
        for source in sorted(sources):
            source_prefix = f"datalake/{layer}/{source}/"
            tables = list_tables(s3, bucket, source_prefix)
            print(f"    {source}  ({len(tables)} tables)")
            for t in sorted(tables):
                print(f"      - {t}")
        print()


# ── CLI ───────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Extract tables from S3 datalake to CSV.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--env",
        choices=["dev", "alpha"],
        default="dev",
        help="Datalake environment (default: dev)",
    )
    parser.add_argument(
        "--source",
        default=None,
        help="Source to extract: DOUGH, OLB, SAFE, ... (default: all)",
    )
    parser.add_argument(
        "--layer",
        default="silver",
        help="Layer to extract: bronze, silver, gold, all (default: silver)",
    )
    parser.add_argument(
        "--table",
        nargs="+",
        default=None,
        help="Specific table(s) to extract (default: all tables)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=20,
        help="Parallel download workers (default: 20, use 40 for OLB)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available sources and tables without downloading",
    )
    args = parser.parse_args()

    bucket = BUCKETS[args.env]
    layers = LAYERS if args.layer == "all" else [args.layer]

    print(f"  Environment : {args.env}")
    print(f"  Bucket      : {bucket}")
    print(f"  AWS Profile : {PROFILE}")

    try:
        s3 = get_s3_client()
    except Exception as e:
        print(f"\n❌ AWS auth error: {e}")
        print("   Run: aws sso login --profile blossom-dev")
        sys.exit(1)

    # ── List mode ──────────────────────────────────────────────────────────────
    if args.list:
        cmd_list(s3, bucket, layers)
        return

    # ── Extract mode ───────────────────────────────────────────────────────────
    for layer in layers:
        if args.source:
            sources = [args.source.upper()]
        else:
            sources = sorted(list_sources(s3, bucket, layer))

        if not sources:
            print(f"  No sources found in layer '{layer}'")
            continue

        for source in sources:
            extract_source(
                s3,
                bucket,
                args.env,
                layer,
                source,
                tables_filter=args.table,
                workers=args.workers,
            )

    print(f"\n✅ Done. Files saved under {ROOT / 'data'}/")


if __name__ == "__main__":
    main()
