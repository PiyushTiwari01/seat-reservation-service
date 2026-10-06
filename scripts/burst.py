#!/usr/bin/env python3
import asyncio
import sys
import uuid
from collections import Counter

import httpx


async def main():
    if len(sys.argv) != 2:
        print("Usage: python scripts/burst.py <BASE_URL>")
        raise SystemExit(1)

    base_url = sys.argv[1].rstrip("/")

    async with httpx.AsyncClient(timeout=60) as client:
        seats = [f"A{i}" for i in range(1, 101)]

        show_response = await client.post(
            f"{base_url}/shows",
            json={
                "name": f"burst-{uuid.uuid4().hex[:8]}",
                "seats": seats,
                "price_paise": 25000,
                "per_user_limit": 4,
            },
        )
        show_response.raise_for_status()
        show_id = show_response.json()["id"]

        total = 500

        async def reserve(i):
            headers = {
                "Authorization": f"Bearer burst-user-{i}",
                "X-Request-ID": str(uuid.uuid4()),
            }
            payload = {
                "seats": ["A1"],
                "idempotency_key": str(uuid.uuid4()),
            }
            response = await client.post(
                f"{base_url}/shows/{show_id}/reserve",
                headers=headers,
                json=payload,
            )
            return response.status_code, response.json()

        results = await asyncio.gather(
            *(reserve(i) for i in range(total)),
            return_exceptions=True,
        )

        counts = Counter()
        errors = []

        for item in results:
            if isinstance(item, Exception):
                counts["client_error"] += 1
                errors.append(str(item))
                continue

            status, body = item
            if status == 201:
                counts["confirmed"] += 1
            elif status == 409:
                code = body.get("detail", {}).get("code", "declined")
                counts[code] += 1
            elif 500 <= status <= 599:
                counts["5xx"] += 1
            else:
                counts[f"http_{status}"] += 1

        state = await client.get(f"{base_url}/shows/{show_id}")
        state.raise_for_status()
        data = state.json()

        print("\n=== HOT SEAT BURST ===")
        print(f"Total requests: {total}")
        for key, value in counts.items():
            print(f"{key}: {value}")

        counts_data = data["counts"]
        reconciliation = sum(counts_data.values())

        print("\n=== RECONCILIATION ===")
        print(f"Total seats: {data['total_seats']}")
        print(f"Available: {counts_data.get('available', 0)}")
        print(f"Held: {counts_data.get('held', 0)}")
        print(f"Confirmed: {counts_data.get('confirmed', 0)}")
        print(f"Sum: {reconciliation}")

        if counts["confirmed"] == 1 and counts["5xx"] == 0 and reconciliation == data["total_seats"]:
            print("\nPASS")
        else:
            print("\nFAIL")
            if errors:
                print("Client errors:", errors[:5])
            raise SystemExit(2)


if __name__ == "__main__":
    asyncio.run(main())
