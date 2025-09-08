import sys
from pathlib import Path
import requests


def upload_csv(base_url: str, csv_path: Path, table_type: str) -> None:
    with csv_path.open('rb') as f:
        files = {'file': (csv_path.name, f, 'text/csv')}
        data = {'table_type': table_type}
        resp = requests.post(f"{base_url}/api/v1/data/upload/csv", files=files, data=data, timeout=120)
    print(f"upload {table_type}: {resp.status_code} {resp.text[:200]}")
    resp.raise_for_status()


def main() -> int:
    base_url = "http://localhost:8000"
    root = Path(__file__).resolve().parents[1]
    sample_dir = root / "sample_data"

    try:
        upload_csv(base_url, sample_dir / "clients.csv", "clients")
    except Exception as e:
        print("clients upload failed:", e)

    try:
        upload_csv(base_url, sample_dir / "orders.csv", "orders")
    except Exception as e:
        print("orders upload failed:", e)

    try:
        upload_csv(base_url, sample_dir / "trades.csv", "trades")
    except Exception as e:
        print("trades upload failed:", e)

    # Verify
    r = requests.get(f"{base_url}/api/v1/data/tables/info", timeout=60)
    print("tables info:", r.status_code, r.json())

    r = requests.get(f"{base_url}/api/v1/dashboard/stats", timeout=60)
    print("dashboard stats:", r.status_code, r.json())

    r = requests.get(f"{base_url}/api/v1/alerts", timeout=60)
    print("alerts count:", r.status_code, len(r.json()))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())


