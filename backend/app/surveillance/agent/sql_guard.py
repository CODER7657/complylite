"""SELECT-only guard for SQL written by the language model.

This is the first of two locks. The second is that the connection itself is opened read-only
with external file access disabled, so even a query that slipped past this check could not
write or read files.
"""
from __future__ import annotations

import re

FORBIDDEN_KEYWORDS = (
    "INSERT", "UPDATE", "DELETE", "MERGE", "CREATE", "DROP", "ALTER", "ATTACH", "DETACH", "COPY", "PRAGMA",
    "INSTALL", "LOAD", "EXPORT", "IMPORT", "CALL", "SET", "RESET", "CHECKPOINT", "VACUUM", "TRUNCATE", "GRANT",
    "REVOKE", "USE", "BEGIN", "COMMIT", "ROLLBACK", "EXECUTE", "PREPARE",
)
FORBIDDEN_FUNCTIONS = (
    "read_csv", "read_csv_auto", "read_parquet", "read_json", "read_json_auto", "read_json_objects", "read_text",
    "read_blob", "read_ndjson", "parquet_scan", "csv_scan", "sniff_csv", "glob", "parquet_metadata",
    "parquet_schema", "iceberg_scan", "delta_scan", "query_table", "query", "getenv",
)
_KW = re.compile(r"\b(" + "|".join(FORBIDDEN_KEYWORDS) + r")\b", re.IGNORECASE)
_FN = re.compile(r"\b(" + "|".join(FORBIDDEN_FUNCTIONS) + r")\s*\(", re.IGNORECASE)
_STR = re.compile(r"'(?:[^']|'')*'")


class SqlGuardError(ValueError):
    pass


def _strip_comments(sql: str) -> str:
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    return re.sub(r"--[^\n]*", " ", sql)


def check_select(sql: str, max_len: int = 4000) -> str:
    """Return the cleaned statement if it is a single read-only SELECT, else raise SqlGuardError."""
    if not isinstance(sql, str) or not sql.strip():
        raise SqlGuardError("empty query")
    if len(sql) > max_len:
        raise SqlGuardError(f"query longer than {max_len} characters")
    body = _strip_comments(sql).strip().rstrip(";").strip()
    bare = _STR.sub("''", body)  # ignore keywords inside string literals
    if ";" in bare:
        raise SqlGuardError("only one statement is allowed")
    if not re.match(r"^(SELECT|WITH)\b", bare, re.IGNORECASE):
        raise SqlGuardError("only SELECT (or WITH ... SELECT) queries are allowed")
    m = _KW.search(bare)
    if m:
        raise SqlGuardError(f"keyword not allowed: {m.group(1).upper()}")
    m = _FN.search(bare)
    if m:
        raise SqlGuardError(f"function not allowed: {m.group(1)}")
    if re.search(r"['\"][^'\"]*\.(csv|parquet|json|duckdb|db|txt)['\"]", body, re.IGNORECASE):
        raise SqlGuardError("file references are not allowed")
    return body


def limited(sql: str, limit: int) -> str:
    return f"SELECT * FROM ({check_select(sql)}) AS q LIMIT {int(limit)}"
