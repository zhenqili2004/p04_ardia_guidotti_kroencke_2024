"""Read-only WRDS extraction, immutable raw annual partitions and source manifest.

Run --check first to inventory columns without retrieving price observations.
Credentials use WRDS_USERNAME (project config) and libpq's ~/.pgpass. No prompts.
"""

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import pandas as pd
import psycopg2
import pyarrow as pa
import pyarrow.parquet as pq

from crsp_schema import choose_source
from settings import CRSP_CORE_END, CRSP_CORE_START, CRSP_EXTRACT_START, config


def connect():
    host, port = "wrds-pgdata.wharton.upenn.edu", 9737
    user = config("WRDS_USERNAME", default=None)
    if not user:
        passfile = Path.home() / ".pgpass"
        if passfile.exists():
            for line in passfile.read_text().splitlines():
                fields = line.split(":", 4)
                if (
                    len(fields) == 5
                    and fields[0] in {host, "*"}
                    and fields[1] in {str(port), "*"}
                    and fields[2] in {"wrds", "*"}
                ):
                    user = fields[3]
                    break
    if not user:
        raise RuntimeError("Set WRDS_USERNAME and a matching ~/.pgpass entry.")
    return psycopg2.connect(
        host=host,
        port=port,
        dbname="wrds",
        user=user,
        connect_timeout=10,
        options="-c default_transaction_read_only=on -c statement_timeout=600000",
    )


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    tmp.replace(path)


def inventory(conn):
    with conn.cursor() as cur:
        cur.execute("""select table_schema, table_name, column_name
            from information_schema.columns where table_schema like 'crsp%%'
            and table_name in ('dsf','dsf_v2','dsenames','stocknames','stksecurityinfohist')
            order by 1,2,ordinal_position""")
        columns = {}
        for schema, table, column in cur.fetchall():
            columns.setdefault((schema, table), set()).add(column)
    return columns


def query(source, history=False):
    mapping = source.history if history else source.daily
    expressions = []
    for alias, field in mapping.items():
        if alias == "valid_from":
            expressions += [
                f"{field}::text as source_valid_from",
                f"greatest({field}, %(start)s::date) as valid_from",
            ]
        elif alias == "valid_to":
            expressions += [
                f"{field}::text as source_valid_to",
                f"least({field}, %(end)s::date) as valid_to",
            ]
        else:
            expressions.append(f"{field} as {alias}")
    if history:
        where = (
            f"{mapping['valid_from']} <= %(end)s and {mapping['valid_to']} >= %(start)s"
        )
        path = source.history_path
    else:
        where = f"{mapping['date']} between %(start)s and %(end)s"
        path = source.daily_path
    # All SQL identifiers originate in hard-coded adapters, never user strings.
    return f"select {', '.join(expressions)} from {path} where {where}"


def extract(conn, sql, params, path):
    """Stream bounded chunks; incomplete downloads never become final files."""
    tmp = path.with_suffix(".parquet.tmp")
    writer = None
    count = 0
    try:
        with conn.cursor(name="crsp_stream") as cur:
            cur.execute(sql, params)
            while True:
                rows = cur.fetchmany(100_000)
                if not rows:
                    break
                frame = pd.DataFrame.from_records(
                    rows, columns=[c.name for c in cur.description]
                )
                # Stable schemas across chunks even if a chunk is all missing.
                strings = {
                    "cusip",
                    "ticker",
                    "price_flag",
                    "cap_flag",
                    "source_valid_from",
                    "source_valid_to",
                    "share_type",
                    "security_type",
                    "security_subtype",
                    "us_incorporated",
                    "issuer_type",
                    "exchange",
                    "condition",
                    "trading_status",
                }
                for col in frame:
                    if col in strings:
                        frame[col] = frame[col].astype("string")
                    elif col in {"date", "valid_from", "valid_to"}:
                        frame[col] = pd.to_datetime(frame[col])
                    elif col in {"permno", "permco", "share_code", "exchange_code"}:
                        frame[col] = pd.to_numeric(frame[col]).astype("Int64")
                    else:
                        frame[col] = pd.to_numeric(frame[col]).astype("float64")
                table = pa.Table.from_pandas(frame, preserve_index=False)
                if writer is None:
                    writer = pq.ParquetWriter(tmp, table.schema, compression="zstd")
                writer.write_table(table)
                count += len(frame)
        if writer is None:
            raise RuntimeError(
                "Extraction returned zero rows; no completed file written."
            )
        writer.close()
        writer = None
        tmp.replace(path)
    finally:
        if writer is not None:
            writer.close()
        tmp.unlink(missing_ok=True)
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--source", choices=["auto", "legacy", "ciz"], default="auto")
    args = parser.parse_args()
    root = Path(config("DATA_DIR")) / "crsp_daily" / "raw"
    root.mkdir(parents=True, exist_ok=True)
    try:
        conn = connect()
    except psycopg2.OperationalError:
        raise SystemExit(
            "WRDS connection failed. Check network access and local credentials; no data extracted."
        ) from None
    try:
        columns = inventory(conn)
        write_json(
            root / "schema_inventory.json",
            {f"{s}.{t}": sorted(c) for (s, t), c in columns.items()},
        )
        source = choose_source(columns, args.source)
        with conn.cursor() as cur:
            for table in (source.daily_path, source.history_path):
                cur.execute(f"select * from {table} limit 0")
        print(
            f"Validated columns and SELECT access: {source.daily_path}, {source.history_path}"
        )
        if args.check:
            return
        spec = dict(
            source=asdict(source),
            extract_start=str(CRSP_EXTRACT_START.date()),
            core_start=str(CRSP_CORE_START.date()),
            end=str(CRSP_CORE_END.date()),
            query_version=1,
            daily_sql=query(source),
            history_sql=query(source, True),
        )
        fingerprint = hashlib.sha256(
            json.dumps(spec, sort_keys=True).encode()
        ).hexdigest()
        manifest_path = root / "manifest.json"
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text())
            if manifest["fingerprint"] != fingerprint:
                raise RuntimeError(
                    "Raw cache uses a different source/window. Use a separate DATA_DIR."
                )
        else:
            manifest = dict(
                spec=spec,
                fingerprint=fingerprint,
                files={},
                started_utc=datetime.now(timezone.utc).isoformat(),
            )
            write_json(manifest_path, manifest)
        jobs = [
            (
                "identifier_history.parquet",
                query(source, True),
                CRSP_EXTRACT_START,
                CRSP_CORE_END,
            )
        ]
        for year in range(CRSP_EXTRACT_START.year, CRSP_CORE_END.year + 1):
            jobs.append(
                (
                    f"daily_{year}.parquet",
                    query(source),
                    max(datetime(year, 1, 1), CRSP_EXTRACT_START),
                    min(datetime(year, 12, 31), CRSP_CORE_END),
                )
            )
        for filename, sql, start, end in jobs:
            path = root / filename
            if filename in manifest["files"] and path.exists():
                if (
                    pq.ParquetFile(path).metadata.num_rows
                    != manifest["files"][filename]["rows"]
                ):
                    raise RuntimeError(f"Cached row count mismatch: {filename}")
                continue
            rows = extract(conn, sql, dict(start=start, end=end), path)
            manifest["files"][filename] = dict(
                rows=rows, retrieved_utc=datetime.now(timezone.utc).isoformat()
            )
            write_json(manifest_path, manifest)
            print(f"Saved {filename}: {rows:,} rows", flush=True)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
