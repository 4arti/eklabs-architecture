"""Discovers real EPAR (European Public Assessment Report) PDFs from EMA and
appends them to evals/manifest.yaml.

EPARs aren't a flat URL list: EMA's search endpoint 401s to automated
fetches, and EPAR PDFs are hosted per-product, not as a bulk archive. This
script:
  1. Downloads EMA's bulk medicine-data Excel export (updated automatically,
     lists every centrally authorised medicine).
  2. Filters to authorised, human-use products.
  3. For each candidate, visits its EMA medicine page and extracts the
     direct EPAR PDF link.
  4. Appends entries to evals/manifest.yaml (capability: ocr and
     citation_checks — spec.md §14 uses the same EPAR set for both).

Usage: python scripts/discover_epars.py --count 50
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pandas as pd
import yaml
from bs4 import BeautifulSoup

MEDICINE_DATA_URL = (
    "https://www.ema.europa.eu/en/documents/report/medicines-output-medicines-report_en.xlsx"
)
USER_AGENT = "eklabs-source-fetcher/1.0 (+regulatory guidance download for internal CTD platform)"
REQUEST_DELAY_SECONDS = 1.5  # be polite to EMA's site between per-product page fetches

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = REPO_ROOT / "evals" / "manifest.yaml"
FIXTURES_DIR = REPO_ROOT / "evals" / "fixtures"

EMA_LICENSE_NOTE = (
    "EMA Legal Notice (ema.europa.eu/en/about-us/about-website/legal-notice): "
    "public documents may be reproduced/distributed for non-commercial and "
    "commercial purposes provided EMA is acknowledged as the source."
)


def find_column(columns: list[str], *candidates: str) -> str | None:
    """Case-insensitive, substring-tolerant match against real column names —
    the exact names weren't known until the file was actually inspected, so
    this stays defensive rather than hardcoding an assumed schema."""
    lowered = {c: c.lower() for c in columns}
    for candidate in candidates:
        for col, low in lowered.items():
            if candidate in low:
                return col
    return None


def load_candidate_products(count: int) -> list[str]:
    print(f"Downloading medicine data index from {MEDICINE_DATA_URL} ...")
    with httpx.Client(headers={"User-Agent": USER_AGENT}, follow_redirects=True) as client:
        response = client.get(MEDICINE_DATA_URL, timeout=60)
        response.raise_for_status()
    xlsx_path = FIXTURES_DIR / "_ema_medicine_data_index.xlsx"
    xlsx_path.parent.mkdir(parents=True, exist_ok=True)
    xlsx_path.write_bytes(response.content)

    # The export has a metadata title row (row 0) and blank rows before the
    # real header — confirmed this session at row index 8, but detect it
    # dynamically rather than hardcoding, in case EMA shifts the layout.
    raw = pd.read_excel(xlsx_path, header=None, nrows=30)
    header_row_idx = None
    for i, row in raw.iterrows():
        if row.astype(str).str.contains("name of medicine", case=False, na=False).any():
            header_row_idx = i
            break
    if header_row_idx is None:
        raise RuntimeError(
            f"Couldn't find the header row (looked for 'name of medicine' in "
            f"the first 30 rows). EMA may have changed the export layout — "
            f"inspect {xlsx_path} by hand."
        )

    df = pd.read_excel(xlsx_path, header=header_row_idx)
    columns = list(df.columns)
    name_col = find_column(columns, "name of medicine", "medicine name", "name")
    status_col = find_column(columns, "medicine status", "authorisation status", "status")
    category_col = find_column(columns, "category", "medicine type", "authorisation type")

    if name_col is None:
        raise RuntimeError(
            f"Couldn't find a medicine-name column among: {columns}. "
            "EMA may have changed the spreadsheet schema — inspect "
            f"{xlsx_path} by hand and update find_column()'s candidates."
        )

    print(
        f"Detected columns — name: {name_col!r}, status: {status_col!r}, category: {category_col!r}"
    )

    filtered = df
    if status_col is not None:
        filtered = filtered[
            filtered[status_col].astype(str).str.contains("authorised", case=False, na=False)
        ]
    if category_col is not None:
        # Keep human-use rows only; EMA's export also lists veterinary medicines.
        filtered = filtered[
            filtered[category_col].astype(str).str.contains("human", case=False, na=False)
        ]

    names = filtered[name_col].dropna().astype(str).drop_duplicates().tolist()
    if not names:
        raise RuntimeError(
            "Filtering produced zero candidates — the status/category filters "
            "may not match this file's actual values. Inspect "
            f"{xlsx_path} by hand before re-running."
        )
    print(f"{len(names)} candidate products after filtering; taking the first {count}.")
    return names[:count]


def slugify(name: str) -> str:
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")


def find_epar_pdf_url(client: httpx.Client, product_name: str) -> tuple[str, str] | None:
    """Visits the product's EMA medicine page and returns (title, pdf_url)
    for its EPAR, or None if no EPAR link is found on that page."""
    slug = slugify(product_name)
    page_url = f"https://www.ema.europa.eu/en/medicines/human/EPAR/{slug}"
    try:
        response = client.get(page_url, timeout=30)
    except httpx.TransportError as exc:
        print(f"    [{product_name}] page fetch failed: {exc}")
        return None
    if response.status_code != 200:
        print(f"    [{product_name}] page {page_url} -> HTTP {response.status_code}")
        return None

    soup = BeautifulSoup(response.text, "html.parser")
    for link in soup.find_all("a", href=True):
        href = link["href"]
        if "epar-public-assessment-report" in href.lower() and href.lower().endswith(".pdf"):
            pdf_url = href if href.startswith("http") else f"https://www.ema.europa.eu{href}"
            # The link's own text is just a generic CTA label ("View") on
            # EMA's page, not a real title — confirmed this session — so
            # always construct the title from the product name instead.
            title = f"{product_name} — EPAR public assessment report"
            return title, pdf_url

    print(f"    [{product_name}] no EPAR PDF link found on {page_url}")
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=50)
    args = parser.parse_args()

    manifest_data: dict = {"entries": []}
    if MANIFEST_PATH.exists():
        manifest_data = yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8")) or {"entries": []}
    existing_ids = {e["id"] for e in manifest_data.get("entries", [])}

    candidates = load_candidate_products(args.count * 2)  # over-fetch: some pages won't resolve

    new_entries = []
    today = datetime.now(UTC).date().isoformat()
    with httpx.Client(headers={"User-Agent": USER_AGENT}, follow_redirects=True) as client:
        for product_name in candidates:
            if len(new_entries) >= args.count:
                break
            entry_id = f"epar-{slugify(product_name)}"
            if entry_id in existing_ids:
                continue

            found = find_epar_pdf_url(client, product_name)
            time.sleep(REQUEST_DELAY_SECONDS)
            if found is None:
                continue
            title, pdf_url = found

            entry = {
                "id": entry_id,
                "path": f"fixtures/ocr/{entry_id}.pdf",
                "title": title,
                "source_url": pdf_url,
                "capability": ["ocr", "citation_checks"],
                "snapshot_date": today,
                "license_note": EMA_LICENSE_NOTE,
            }
            new_entries.append(entry)
            print(f"[found] {entry_id} <- {pdf_url}")

    if not new_entries:
        print("No new EPARs discovered — nothing to append.")
        return 1

    manifest_data.setdefault("entries", []).extend(new_entries)
    MANIFEST_PATH.write_text(
        yaml.safe_dump(manifest_data, sort_keys=False, allow_unicode=True, width=100),
        encoding="utf-8",
    )
    print(f"\nAppended {len(new_entries)} EPAR entries to {MANIFEST_PATH}")
    print("Run scripts/fetch_sources.py evals/manifest.yaml to actually download them.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
