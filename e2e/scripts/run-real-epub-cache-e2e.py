#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import requests


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run real-data EPUB cache management E2E flow against local stack."
    )
    parser.add_argument("--api-url", default="http://localhost:8000/api")
    parser.add_argument("--admin-email", default="admin@admin.com")
    parser.add_argument("--admin-password", default="12345678")
    parser.add_argument(
        "--ebooks-dir",
        default="/Users/johnson/Downloads/Organized/Ebooks",
        help="Directory containing real .epub files.",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=3,
        help="How many epub files to include in the multi-book batch.",
    )
    parser.add_argument(
        "--batch-timeout-seconds",
        type=int,
        default=300,
        help="Timeout for batch completion polling.",
    )
    parser.add_argument(
        "--require-non-empty-entries",
        action="store_true",
        help="Fail if all selected books produce zero matched entries.",
    )
    return parser.parse_args()


def choose_epubs(root: Path, count: int) -> list[Path]:
    files = sorted([p for p in root.glob("*.epub") if p.is_file()])
    if len(files) < count:
        raise SystemExit(f"Need at least {count} .epub files in {root}, found {len(files)}")
    return files[:count]


def login(session: requests.Session, api_url: str, email: str, password: str) -> str:
    response = session.post(
        f"{api_url}/auth/login",
        json={"email": email, "password": password},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def create_batch(
    session: requests.Session,
    api_url: str,
    token: str,
    batch_name: str,
    ebooks: list[Path],
) -> dict:
    headers = {"Authorization": f"Bearer {token}"}
    files = []
    handles = []
    try:
        for path in ebooks:
            handle = path.open("rb")
            handles.append(handle)
            files.append(("files", (path.name, handle, "application/epub+zip")))
        response = session.post(
            f"{api_url}/admin/import-batches/epub",
            headers=headers,
            data={"batch_name": batch_name},
            files=files,
            timeout=180,
        )
        response.raise_for_status()
        return response.json()
    finally:
        for handle in handles:
            handle.close()


def wait_for_batch_terminal(
    session: requests.Session,
    api_url: str,
    token: str,
    batch_id: str,
    timeout_seconds: int,
) -> dict:
    headers = {"Authorization": f"Bearer {token}"}
    deadline = time.time() + timeout_seconds
    last_summary = None
    while time.time() < deadline:
        response = session.get(f"{api_url}/admin/import-batches/{batch_id}", headers=headers, timeout=30)
        response.raise_for_status()
        summary = response.json()
        last_summary = summary
        active_jobs = int(summary.get("active_jobs") or 0)
        print(
            "[batch]",
            json.dumps(
                {
                    "id": batch_id,
                    "completed": summary.get("completed_jobs"),
                    "failed": summary.get("failed_jobs"),
                    "active": active_jobs,
                }
            ),
        )
        if active_jobs == 0:
            return summary
        time.sleep(2)
    raise TimeoutError(f"Batch {batch_id} did not reach terminal state: {last_summary}")


def assert_source_entries_state(
    session: requests.Session, api_url: str, token: str, source_id: str
) -> int:
    headers = {"Authorization": f"Bearer {token}"}
    detail = session.get(f"{api_url}/admin/import-sources/{source_id}", headers=headers, timeout=30)
    detail.raise_for_status()
    entries = session.get(
        f"{api_url}/admin/import-sources/{source_id}/entries?limit=10",
        headers=headers,
        timeout=30,
    )
    if entries.status_code != 200:
        raise RuntimeError(f"Entries query failed for source {source_id}: {entries.status_code} {entries.text}")
    payload = entries.json()
    total = int(payload.get("total") or 0)
    print(
        "[source]",
        json.dumps(
            {
                "id": source_id,
                "status": detail.json().get("status"),
                "deleted_at": detail.json().get("deleted_at"),
                "entries_total": total,
            }
        ),
    )
    return total


def main() -> None:
    args = parse_args()
    ebooks_root = Path(args.ebooks_dir)
    if not ebooks_root.exists():
        raise SystemExit(f"Ebooks directory not found: {ebooks_root}")

    selected_books = choose_epubs(ebooks_root, args.count)
    print("[books]", json.dumps([str(path) for path in selected_books], ensure_ascii=False))

    session = requests.Session()
    token = login(session, args.api_url, args.admin_email, args.admin_password)
    headers = {"Authorization": f"Bearer {token}"}

    created = create_batch(
        session,
        args.api_url,
        token,
        batch_name="real-ebooks-e2e-batch",
        ebooks=selected_books,
    )
    batch = created["batch"]
    jobs = created["jobs"]
    source_ids = [job["import_source_id"] for job in jobs if job.get("import_source_id")]
    print("[create]", json.dumps({"batch": batch, "jobs": jobs}, default=str))

    wait_for_batch_terminal(
        session,
        args.api_url,
        token,
        batch_id=batch["id"],
        timeout_seconds=args.batch_timeout_seconds,
    )

    jobs_response = session.get(
        f"{args.api_url}/admin/import-batches/{batch['id']}/jobs?limit=100",
        headers=headers,
        timeout=30,
    )
    jobs_response.raise_for_status()
    print("[jobs]", json.dumps(jobs_response.json(), default=str))

    entry_totals: list[int] = []
    for source_id in source_ids:
        entry_totals.append(assert_source_entries_state(session, args.api_url, token, source_id))
    if args.require_non_empty_entries and not any(total > 0 for total in entry_totals):
        raise RuntimeError(
            f"All selected books produced zero matched entries: {entry_totals}. "
            "Populate lexicon words first, then rerun."
        )

    first_source = source_ids[0]
    delete_response = session.delete(
        f"{args.api_url}/admin/import-sources/{first_source}?delete_mode=cache_only",
        headers=headers,
        timeout=30,
    )
    delete_response.raise_for_status()
    print("[delete-single]", delete_response.text)

    blocked_entries = session.get(
        f"{args.api_url}/admin/import-sources/{first_source}/entries?limit=10",
        headers=headers,
        timeout=30,
    )
    if blocked_entries.status_code != 410:
        raise RuntimeError(
            f"Expected 410 after source delete for entries endpoint, got {blocked_entries.status_code}: {blocked_entries.text}"
        )
    print("[delete-single-check]", blocked_entries.text)

    remaining = source_ids[1:]
    if remaining:
        bulk_response = session.post(
            f"{args.api_url}/admin/import-sources/bulk-delete",
            headers={**headers, "Content-Type": "application/json"},
            data=json.dumps({"source_ids": remaining, "delete_mode": "cache_only"}),
            timeout=30,
        )
        bulk_response.raise_for_status()
        print("[delete-bulk]", bulk_response.text)

    # Re-upload first book to verify re-activation path.
    regenerated = create_batch(
        session,
        args.api_url,
        token,
        batch_name="real-ebooks-reactivation-check",
        ebooks=[selected_books[0]],
    )
    regen_source_id = regenerated["jobs"][0].get("import_source_id")
    print("[reupload]", json.dumps(regenerated, default=str))
    if regen_source_id != first_source:
        raise RuntimeError(
            f"Expected re-upload to resolve same source id. deleted={first_source}, reupload={regen_source_id}"
        )
    print("[done] real EPUB cache scenario complete")


if __name__ == "__main__":
    main()
