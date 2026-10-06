import asyncio
import sys
import uuid
from collections import Counter

import httpx


async def main():
    if len(sys.argv) != 2:
        print("Usage: python scripts/idempotency_burst.py <BASE_URL>")
        raise SystemExit(1)

    base_url = sys.argv[1].rstrip("/")

    async with httpx.AsyncClient(timeout=60) as client:

        # Create fresh show
        seats = [f"A{i}" for i in range(1, 11)]

        response = await client.post(
            f"{base_url}/shows",
            json={
                "name": f"idempotency-{uuid.uuid4().hex[:8]}",
                "seats": seats,
                "price_paise": 25000,
                "per_user_limit": 4,
            },
        )

        response.raise_for_status()
        show_id = response.json()["id"]

        total = 500

        # EXACT SAME user + SAME seat + SAME idempotency key
        user_id = "idempotency-test-user"
        idempotency_key = f"storm-{uuid.uuid4()}"

        async def reserve(i):
            response = await client.post(
                f"{base_url}/shows/{show_id}/reserve",
                headers={
                    "Authorization": f"Bearer {user_id}",
                    "X-Request-ID": str(uuid.uuid4()),
                },
                json={
                    "seats": ["A1"],
                    "idempotency_key": idempotency_key,
                },
            )

            return response.status_code, response.json()

        results = await asyncio.gather(
            *(reserve(i) for i in range(total)),
            return_exceptions=True,
        )

        counts = Counter()
        reservation_ids = set()
        errors = []

        for item in results:
            if isinstance(item, Exception):
                counts["client_error"] += 1
                errors.append(str(item))
                continue

            status, body = item

            if status == 201:
                if body.get("idempotent_replay"):
                    counts["replay"] += 1
                else:
                    counts["confirmed"] += 1

                if body.get("reservation_id"):
                    reservation_ids.add(body["reservation_id"])

            elif status == 409:
                code = body.get("detail", {}).get("code", "409")
                counts[code] += 1

            elif 500 <= status <= 599:
                counts["5xx"] += 1

            else:
                counts[f"http_{status}"] += 1

        # Check final show state
        state_response = await client.get(
            f"{base_url}/shows/{show_id}"
        )
        state_response.raise_for_status()

        state = state_response.json()
        counts_data = state["counts"]

        print("\n=== IDEMPOTENCY STORM ===")
        print(f"Total requests: {total}")

        for key, value in counts.items():
            print(f"{key}: {value}")

        print(f"Unique reservation IDs: {len(reservation_ids)}")

        print("\n=== RECONCILIATION ===")
        print(f"Total seats: {state['total_seats']}")
        print(f"Available: {counts_data.get('available', 0)}")
        print(f"Held: {counts_data.get('held', 0)}")
        print(f"Confirmed: {counts_data.get('confirmed', 0)}")

        reconciliation = sum(counts_data.values())
        print(f"Sum: {reconciliation}")

        passed = (
            counts["confirmed"] == 1
            and counts["replay"] == total - 1
            and counts["5xx"] == 0
            and len(reservation_ids) == 1
            and counts_data.get("confirmed", 0) == 1
            and reconciliation == state["total_seats"]
        )

        if passed:
            print("\nPASS")
        else:
            print("\nFAIL")

            if errors:
                print("Client errors:", errors[:5])

            raise SystemExit(2)


if __name__ == "__main__":
    asyncio.run(main())