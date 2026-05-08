"""
Extract DOUGH tables from S3 datalake (bronze & silver) to CSV files.
Reads all parquet files per table and writes a single CSV per table.

Usage:
    python extract_dough_to_csv.py --env dev      # blossom-analytics-datalake-dev
    python extract_dough_to_csv.py --env alpha    # blossom-analytics-datalake-alpha
"""
import argparse
import boto3
import pandas as pd
import pyarrow.parquet as pq
import io
import os

BUCKETS = {
    "dev":   "blossom-analytics-datalake-dev",
    "alpha": "blossom-analytics-datalake-alpha",
}
LAYERS = ["bronze", "silver"]
DOUGH_PREFIX = "datalake/{layer}/DOUGH/"
PROFILE = "blossom-dev"

SKIP_TABLES = {"_bronze_watermark", "_silver_watermark", "logs", "migrations", "seeder_tracking"}


def get_s3_client():
    session = boto3.Session(profile_name=PROFILE)
    return session.client("s3")


def list_parquet_files(s3, bucket, prefix):
    files = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith(".parquet"):
                files.append(key)
    return files


def read_parquet_files(s3, bucket, keys):
    dfs = []
    for key in keys:
        try:
            resp = s3.get_object(Bucket=bucket, Key=key)
            buf = io.BytesIO(resp["Body"].read())
            df = pq.read_table(buf).to_pandas()
            dfs.append(df)
        except Exception as e:
            print(f"  ⚠️  Error reading {key}: {e}")
    if not dfs:
        return None
    return pd.concat(dfs, ignore_index=True)


def list_tables(s3, bucket, prefix):
    resp = s3.list_objects_v2(Bucket=bucket, Prefix=prefix, Delimiter="/")
    return [
        cp["Prefix"].split("/")[-2]
        for cp in resp.get("CommonPrefixes", [])
    ]


def extract_layer(s3, bucket, layer, output_base):
    prefix = DOUGH_PREFIX.format(layer=layer)
    output_dir = os.path.join(output_base, layer)
    os.makedirs(output_dir, exist_ok=True)

    tables = list_tables(s3, bucket, prefix)
    tables = [t for t in tables if t not in SKIP_TABLES]

    print(f"\n{'='*50}")
    print(f"Layer: {layer.upper()} — {len(tables)} tables found")
    print(f"{'='*50}")

    for table in tables:
        table_prefix = f"{prefix}{table}/data/"
        print(f"\n→ {table}", end="", flush=True)

        parquet_files = list_parquet_files(s3, bucket, table_prefix)
        if not parquet_files:
            print(" [NO DATA]")
            continue

        print(f" ({len(parquet_files)} parquet files)", end="", flush=True)
        df = read_parquet_files(s3, bucket, parquet_files)

        if df is None or df.empty:
            print(" [EMPTY]")
            continue

        df = df.drop_duplicates()

        out_path = os.path.join(output_dir, f"{table}.csv")
        df.to_csv(out_path, index=False)
        print(f" ✓ {len(df):,} rows → {table}.csv")


def main():
    parser = argparse.ArgumentParser(description="Extract DOUGH tables from S3 datalake to CSV.")
    parser.add_argument("--env", choices=["dev", "alpha"], default="dev",
                        help="Datalake environment (default: dev)")
    args = parser.parse_args()

    bucket = BUCKETS[args.env]
    output_base = os.path.join(os.path.dirname(__file__), "..", "data", "dough", args.env)

    print(f"Environment : {args.env}")
    print(f"Bucket      : {bucket}")
    print(f"Output      : {os.path.abspath(output_base)}")
    print(f"AWS Profile : {PROFILE}")

    s3 = get_s3_client()

    for layer in LAYERS:
        extract_layer(s3, bucket, layer, output_base)

    print("\n✅ Extraction complete.")
    print(f"📁 Files saved to: {os.path.abspath(output_base)}")


if __name__ == "__main__":
    main()



def get_s3_client():
    session = boto3.Session(profile_name=PROFILE)
    return session.client("s3")


def list_parquet_files(s3, bucket, prefix):
    files = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith(".parquet"):
                files.append(key)
    return files


def read_parquet_files(s3, bucket, keys):
    dfs = []
    for key in keys:
        try:
            resp = s3.get_object(Bucket=bucket, Key=key)
            buf = io.BytesIO(resp["Body"].read())
            df = pq.read_table(buf).to_pandas()
            dfs.append(df)
        except Exception as e:
            print(f"  ⚠️  Error reading {key}: {e}")
    if not dfs:
        return None
    return pd.concat(dfs, ignore_index=True)


def list_tables(s3, bucket, prefix):
    resp = s3.list_objects_v2(Bucket=bucket, Prefix=prefix, Delimiter="/")
    return [
        cp["Prefix"].split("/")[-2]
        for cp in resp.get("CommonPrefixes", [])
    ]


def extract_layer(s3, layer):
    prefix = DOUGH_PREFIX.format(layer=layer)
    output_dir = os.path.join(OUTPUT_BASE, layer)
    os.makedirs(output_dir, exist_ok=True)

    tables = list_tables(s3, BUCKET, prefix)
    tables = [t for t in tables if t not in SKIP_TABLES]

    print(f"\n{'='*50}")
    print(f"Layer: {layer.upper()} — {len(tables)} tables found")
    print(f"{'='*50}")

    for table in tables:
        table_prefix = f"{prefix}{table}/data/"
        print(f"\n→ {table}", end="", flush=True)

        parquet_files = list_parquet_files(s3, BUCKET, table_prefix)
        if not parquet_files:
            print(" [NO DATA]")
            continue

        print(f" ({len(parquet_files)} parquet files)", end="", flush=True)
        df = read_parquet_files(s3, BUCKET, parquet_files)

        if df is None or df.empty:
            print(" [EMPTY]")
            continue

        df = df.drop_duplicates()

        out_path = os.path.join(output_dir, f"{table}.csv")
        df.to_csv(out_path, index=False)
        print(f" ✓ {len(df):,} rows → {table}.csv")


def main():
    print("Connecting to AWS (profile: blossom-dev)...")
    s3 = get_s3_client()

    for layer in LAYERS:
        extract_layer(s3, layer)

    print("\n✅ Extraction complete.")
    print(f"📁 Files saved to: {os.path.abspath(OUTPUT_BASE)}")


if __name__ == "__main__":
    main()
