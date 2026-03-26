#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
import socket
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List


API_URL = "https://dadesobertes.valls.cat/api/3/action/package_search"
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
CATALOG_PATH = DATA_DIR / "catalog.json"
REQUEST_TIMEOUT = 12


def slugify(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return normalized or "dataset"


def fetch_json(url: str) -> Dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "valls-local-catalog/1.0",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
        return json.load(response)


def download_text(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "valls-local-catalog/1.0",
            "Accept": "text/csv,*/*",
        },
    )
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def sample_rows(csv_text: str, limit: int = 5) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    reader = csv.DictReader(csv_text.splitlines())
    for index, row in enumerate(reader):
        if index >= limit:
            break
        rows.append({key: (value or "") for key, value in row.items()})
    return rows


def detect_columns(samples: List[Dict[str, str]]) -> Dict[str, Any]:
    if not samples:
        return {"columns": [], "geo_columns": [], "numeric_candidates": []}

    columns = list(samples[0].keys())
    geo_columns = [
        column
        for column in columns
        if any(token in column.lower() for token in ("lat", "lon", "long", "xutm", "yutm"))
    ]

    numeric_counter: Counter[str] = Counter()
    for row in samples:
        for column, value in row.items():
            stripped = value.strip().replace(",", ".")
            if not stripped:
                continue
            try:
                float(stripped)
            except ValueError:
                continue
            numeric_counter[column] += 1

    numeric_candidates = [column for column, count in numeric_counter.items() if count >= max(1, len(samples) - 1)]
    return {
        "columns": columns,
        "geo_columns": geo_columns,
        "numeric_candidates": numeric_candidates,
    }


def build_api_url(rows: int, start: int) -> str:
    params = urllib.parse.urlencode(
        {
            "rows": rows,
            "start": start,
            "include_private": "false",
        }
    )
    return f"{API_URL}?{params}"


def ensure_dirs() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)


def fetch_all_packages() -> List[Dict[str, Any]]:
    packages: List[Dict[str, Any]] = []
    start = 0
    rows = 100

    while True:
        payload = fetch_json(build_api_url(rows=rows, start=start))
        if not payload.get("success"):
            raise RuntimeError("La API de CKAN ha devuelto success=false")

        result = payload["result"]
        batch = result.get("results", [])
        packages.extend(batch)
        start += len(batch)

        if start >= result.get("count", 0) or not batch:
            return packages


def choose_csv_resources(package: Dict[str, Any]) -> List[Dict[str, Any]]:
    resources = []
    for resource in package.get("resources", []):
        if (resource.get("format") or "").upper() != "CSV":
            continue
        url = resource.get("url") or ""
        if not url.startswith("http"):
            continue
        resources.append(resource)
    return resources


def write_resource(dataset_slug: str, resource: Dict[str, Any]) -> Dict[str, Any] | None:
    resource_slug = slugify(resource.get("name") or resource.get("id") or "resource")
    filename = f"{dataset_slug}__{resource_slug}.csv"
    destination = RAW_DIR / filename
    try:
        csv_text = download_text(resource["url"])
    except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
        print(f"Aviso: no se pudo descargar {resource.get('name')}: {exc}", file=sys.stderr)
        return None

    destination.write_text(csv_text, encoding="utf-8")

    samples = sample_rows(csv_text)
    detected = detect_columns(samples)

    return {
        "id": resource.get("id"),
        "name": resource.get("name"),
        "description": resource.get("description") or "",
        "format": resource.get("format"),
        "source_url": resource.get("url"),
        "local_path": f"data/raw/{filename}",
        "downloaded_bytes": destination.stat().st_size,
        "sample_rows": samples,
        **detected,
    }


def transform_package(package: Dict[str, Any]) -> Dict[str, Any] | None:
    csv_resources = choose_csv_resources(package)
    if not csv_resources:
        return None

    dataset_slug = slugify(package.get("name") or package.get("title") or package["id"])
    groups = [group.get("display_name") for group in package.get("groups", []) if group.get("display_name")]
    organization = (package.get("organization") or {}).get("title") or ""

    resources = []
    for resource in csv_resources:
        resource_info = write_resource(dataset_slug, resource)
        if resource_info:
            resources.append(resource_info)

    if not resources:
        return None

    return {
        "id": package.get("id"),
        "slug": dataset_slug,
        "title": package.get("title"),
        "name": package.get("name"),
        "notes": package.get("notes") or "",
        "license_title": package.get("license_title") or "",
        "metadata_created": package.get("metadata_created"),
        "metadata_modified": package.get("metadata_modified"),
        "organization": organization,
        "groups": groups,
        "resource_count": len(resources),
        "resources": resources,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Sincroniza datasets CSV de dadesobertes.valls.cat")
    parser.add_argument("--limit", type=int, default=None, help="Número máximo de datasets CSV a descargar")
    args = parser.parse_args()

    ensure_dirs()

    try:
        packages = fetch_all_packages()
    except (RuntimeError, urllib.error.URLError) as exc:
        print(f"Error consultando la API de Valls: {exc}", file=sys.stderr)
        return 1

    catalog_items: List[Dict[str, Any]] = []
    for package in packages:
        if args.limit is not None and len(catalog_items) >= args.limit:
            break
        print(f"Procesando dataset: {package.get('title')}", file=sys.stderr)
        transformed = transform_package(package)
        if transformed:
            catalog_items.append(transformed)

    group_names = sorted({group for item in catalog_items for group in item["groups"]})
    organizations = sorted({item["organization"] for item in catalog_items if item["organization"]})

    catalog = {
        "source": "https://dadesobertes.valls.cat",
        "generated_at": __import__("datetime").datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "dataset_count": len(catalog_items),
        "groups": group_names,
        "organizations": organizations,
        "datasets": catalog_items,
    }

    CATALOG_PATH.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Catálogo generado en {CATALOG_PATH}")
    print(f"Datasets CSV descargados: {len(catalog_items)}")
    build_script = BASE_DIR / "scripts" / "build_transparency_index.py"
    subprocess.run([sys.executable, str(build_script)], check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
