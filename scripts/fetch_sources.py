"""Downloads the files listed in a manifest.yaml into place.

Usage: python scripts/fetch_sources.py <manifest.yaml> [--insecure-hosts HOST ...]

Reads `entries: [{id, path, source_url, ...}, ...]` from the given
manifest.yaml and downloads each `source_url` to `path` (resolved relative to
the manifest's own directory), skipping files that already exist so re-runs
are cheap. Retries with backoff on transient failures — database.ich.org in
particular rate-limits concurrent requests but succeeds on sequential retry.

TLS verification is on by default for every host. A handful of legacy
regulatory hosts (e.g. estri.ich.org) serve broken/self-signed certificates;
rather than disabling verification globally, pass the exact host via
--insecure-hosts to skip verification for that host only, and a warning is
printed every time that happens.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx
import yaml

RETRIES = 4
BACKOFF_SECONDS = 3
TIMEOUT_SECONDS = 60
USER_AGENT = "eklabs-source-fetcher/1.0 (+regulatory guidance download for internal CTD platform)"


def load_entries(manifest_path: Path) -> list[dict]:
    data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    return data.get("entries") or []


def fetch_one(client: httpx.Client, url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    last_error: Exception | None = None
    for attempt in range(1, RETRIES + 1):
        try:
            with client.stream("GET", url, timeout=TIMEOUT_SECONDS) as response:
                response.raise_for_status()
                tmp = dest.with_suffix(dest.suffix + ".part")
                with tmp.open("wb") as f:
                    for chunk in response.iter_bytes():
                        f.write(chunk)
                tmp.replace(dest)
            return
        except (httpx.TransportError, httpx.HTTPStatusError) as exc:
            last_error = exc
            if attempt < RETRIES:
                wait = BACKOFF_SECONDS * attempt
                print(f"    retry {attempt}/{RETRIES} after {wait}s ({exc})")
                time.sleep(wait)
    raise RuntimeError(f"failed after {RETRIES} attempts: {last_error}") from last_error


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="path to a manifest.yaml")
    parser.add_argument(
        "--insecure-hosts",
        nargs="*",
        default=[],
        help="hostnames to skip TLS verification for (known-broken legacy hosts only)",
    )
    args = parser.parse_args()

    manifest_path: Path = args.manifest.resolve()
    base_dir = manifest_path.parent
    entries = load_entries(manifest_path)
    if not entries:
        print(f"{manifest_path}: no entries, nothing to fetch")
        return 0

    insecure_hosts = set(args.insecure_hosts)
    headers = {"User-Agent": USER_AGENT}
    secure_client = httpx.Client(headers=headers, follow_redirects=True)
    insecure_client = httpx.Client(headers=headers, follow_redirects=True, verify=False)

    ok = 0
    skipped = 0
    failed: list[str] = []
    for entry in entries:
        entry_id = entry["id"]
        url = entry["source_url"]
        dest = base_dir / entry["path"]
        host = urlparse(url).hostname or ""

        if dest.exists():
            skipped += 1
            print(f"[skip]  {entry_id} -> {dest} (already present)")
            continue

        client = secure_client
        if host in insecure_hosts:
            print(f"    WARNING: TLS verification disabled for {host} ({entry_id})")
            client = insecure_client

        print(f"[fetch] {entry_id} <- {url}")
        try:
            fetch_one(client, url, dest)
            ok += 1
        except Exception as exc:  # noqa: BLE001 - report and continue with the rest
            failed.append(entry_id)
            print(f"    FAILED: {exc}")

    secure_client.close()
    insecure_client.close()

    print(f"\n{ok} fetched, {skipped} already present, {len(failed)} failed")
    if failed:
        print("Failed ids: " + ", ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
