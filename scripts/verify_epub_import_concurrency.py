import asyncio
import json
import os
import random
import time
from pathlib import Path

import httpx

API_URL = os.environ.get("CONCURRENCY_API_URL", "http://127.0.0.1:18002/api")
EPUB_PATH = Path(
    os.environ.get(
        "CONCURRENCY_EPUB_PATH",
        "e2e/tests/fixtures/epub/valid-minimal.epub",
    )
)
TIMEOUT_SECONDS = float(os.environ.get("CONCURRENCY_TIMEOUT_SECONDS", "120"))


def _unique_email(prefix: str) -> str:
    return f"{prefix}-{int(time.time() * 1000)}-{random.randint(1000, 9999)}@example.com"


async def register_user(client: httpx.AsyncClient, prefix: str) -> dict:
    email = _unique_email(prefix)
    response = await client.post(
        f"{API_URL}/auth/register",
        json={"email": email, "password": "password123"},
    )
    response.raise_for_status()
    body = response.json()
    return {
        "email": email,
        "token": body["access_token"],
    }


async def upload_import(client: httpx.AsyncClient, token: str, list_name: str) -> dict:
    with EPUB_PATH.open("rb") as epub_file:
        response = await client.post(
            f"{API_URL}/word-lists/import",
            headers={"Authorization": f"Bearer {token}"},
            data={"list_name": list_name},
            files={"file": (EPUB_PATH.name, epub_file, "application/epub+zip")},
        )
    response.raise_for_status()
    return response.json()


async def wait_for_job(client: httpx.AsyncClient, token: str, job_id: str) -> dict:
    deadline = time.monotonic() + TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        response = await client.get(
            f"{API_URL}/import-jobs/{job_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        response.raise_for_status()
        body = response.json()
        if body["status"] in {"completed", "failed"}:
            return body
        await asyncio.sleep(1.0)
    raise TimeoutError(f"Timed out waiting for import job {job_id}")


async def main() -> None:
    if not EPUB_PATH.exists():
        raise FileNotFoundError(f"EPUB fixture not found: {EPUB_PATH}")

    async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
        user_one, user_two = await asyncio.gather(
            register_user(client, "concurrency-a"),
            register_user(client, "concurrency-b"),
        )

        uploads = await asyncio.gather(
            upload_import(client, user_one["token"], "Concurrent Import A"),
            upload_import(client, user_two["token"], "Concurrent Import B"),
        )

        job_one = await wait_for_job(client, user_one["token"], uploads[0]["id"])
        job_two = await wait_for_job(client, user_two["token"], uploads[1]["id"])

        result = {
            "job_ids": [uploads[0]["id"], uploads[1]["id"]],
            "statuses": [job_one["status"], job_two["status"]],
            "import_source_ids": [job_one["import_source_id"], job_two["import_source_id"]],
            "matched_entry_counts": [job_one["matched_entry_count"], job_two["matched_entry_count"]],
        }
        print(json.dumps(result, indent=2))

        assert job_one["status"] == "completed"
        assert job_two["status"] == "completed"
        assert job_one["import_source_id"] == job_two["import_source_id"]
        assert job_one["matched_entry_count"] > 0
        assert job_two["matched_entry_count"] > 0


if __name__ == "__main__":
    asyncio.run(main())
