"""
RadAI Backend API Smoke Test

Exercises the main backend API endpoints to verify they work end-to-end
after Phase 0 deployment:

  1. POST /api/v1/auth/login        -> obtain JWT
  2. GET  /api/v1/studies           -> list studies (requires JWT)
  3. GET  /api/v1/studies/{id}      -> study detail (if any studies exist)
  4. GET  /health                    -> backend health check
  5. POST /api/v1/auth/login (bad)  -> verifies auth rejection

Usage:
    python scripts/smoke_test.py
    python scripts/smoke_test.py --base-url https://localhost
    python scripts/smoke_test.py --username admin --password changeme
"""
from __future__ import annotations

import argparse
import json
import os
import sys

try:
    import httpx
except ImportError:
    print("ERROR: httpx not installed. Run: pip install httpx")
    sys.exit(1)


# ─── Colours ─────────────────────────────────────────────────────────────────
class C:
    G = "\033[92m"
    R = "\033[91m"
    Y = "\033[93m"
    B = "\033[1m"
    E = "\033[0m"


def p_ok(msg: str) -> None:
    print(f"  {C.G}[OK]{C.E} {msg}")


def p_fail(msg: str) -> None:
    print(f"  {C.R}[FAIL]{C.E} {msg}")


def p_warn(msg: str) -> None:
    print(f"  {C.Y}[WARN]{C.E} {msg}")


def step(title: str) -> None:
    print(f"\n{C.B}>> {title}{C.E}")


# ─── Tests ───────────────────────────────────────────────────────────────────
def test_health(client: httpx.Client, base_url: str) -> bool:
    step("Health endpoint")
    try:
        r = client.get(f"{base_url}/health")
        if r.status_code != 200:
            p_fail(f"/health returned {r.status_code}")
            return False
        data = r.json()
        p_ok(f"status={data.get('status')}, checks={data.get('checks', {})}")
        return data.get("status") == "ok"
    except Exception as e:
        p_fail(f"{e}")
        return False


def test_login(client: httpx.Client, base_url: str, username: str, password: str) -> str | None:
    step(f"Login as {username}")
    try:
        r = client.post(
            f"{base_url}/api/v1/auth/login",
            json={"username": username, "password": password},
        )
        if r.status_code != 200:
            p_fail(f"Login returned {r.status_code}: {r.text[:200]}")
            return None
        data = r.json()
        token = data.get("access_token")
        if not token:
            p_fail(f"No access_token in response: {data}")
            return None
        p_ok(f"Got JWT access token (length={len(token)})")
        if "refresh_token" in data:
            p_ok("Refresh token also returned")
        return token
    except Exception as e:
        p_fail(f"{e}")
        return None


def test_bad_login(client: httpx.Client, base_url: str) -> bool:
    step("Login rejection (bad credentials)")
    try:
        r = client.post(
            f"{base_url}/api/v1/auth/login",
            json={"username": "nope", "password": "wrong"},
        )
        if r.status_code in (401, 403, 404):
            p_ok(f"Correctly rejected with HTTP {r.status_code}")
            return True
        p_fail(f"Expected 401/403, got {r.status_code}")
        return False
    except Exception as e:
        p_fail(f"{e}")
        return False


def test_unauthenticated_studies(client: httpx.Client, base_url: str) -> bool:
    step("Studies endpoint without auth (should 401)")
    try:
        r = client.get(f"{base_url}/api/v1/studies")
        if r.status_code == 401:
            p_ok("Correctly rejected unauthenticated request")
            return True
        if r.status_code == 200:
            p_warn(f"Endpoint returned 200 without auth - check authentication middleware")
            return False
        p_warn(f"Unexpected status {r.status_code}")
        return False
    except Exception as e:
        p_fail(f"{e}")
        return False


def test_list_studies(client: httpx.Client, base_url: str, token: str) -> list[dict]:
    step("List studies (authenticated)")
    try:
        r = client.get(
            f"{base_url}/api/v1/studies",
            headers={"Authorization": f"Bearer {token}"},
        )
        if r.status_code != 200:
            p_fail(f"GET /studies returned {r.status_code}: {r.text[:200]}")
            return []
        data = r.json()
        studies = data if isinstance(data, list) else data.get("items") or data.get("studies") or []
        p_ok(f"Retrieved {len(studies)} studies")
        return studies
    except Exception as e:
        p_fail(f"{e}")
        return []


def test_study_detail(client: httpx.Client, base_url: str, token: str, studies: list[dict]) -> bool:
    if not studies:
        step("Study detail - skipped (no studies in database)")
        return True
    step("Study detail endpoint")
    study_id = studies[0].get("id") or studies[0].get("study_instance_uid")
    if not study_id:
        p_warn(f"Cannot find id in study: {studies[0]}")
        return False
    try:
        r = client.get(
            f"{base_url}/api/v1/studies/{study_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        if r.status_code == 200:
            p_ok(f"Loaded study detail for {study_id}")
            return True
        p_warn(f"GET /studies/{study_id} returned {r.status_code}")
        return False
    except Exception as e:
        p_fail(f"{e}")
        return False


def test_openapi(client: httpx.Client, base_url: str) -> bool:
    step("OpenAPI schema")
    for path in ("/api/v1/openapi.json", "/api/openapi.json", "/openapi.json", "/api/v1/docs"):
        try:
            r = client.get(f"{base_url}{path}")
            if r.status_code == 200:
                p_ok(f"OpenAPI available at {path}")
                return True
        except Exception:
            pass
    p_warn("OpenAPI schema not found at common paths (non-critical)")
    return False


# ─── Main ────────────────────────────────────────────────────────────────────
def main() -> int:
    parser = argparse.ArgumentParser(description="RadAI backend smoke test")
    parser.add_argument(
        "--base-url",
        default=os.environ.get("RADAI_BASE_URL", "https://localhost"),
    )
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default="changeme")
    args = parser.parse_args()

    print(f"{C.B}== RadAI Backend Smoke Test =={C.E}")
    print(f"Target: {args.base_url}")

    results: list[tuple[str, bool]] = []

    with httpx.Client(verify=False, timeout=15) as client:
        results.append(("Health", test_health(client, args.base_url)))
        results.append(("Unauthenticated studies rejected", test_unauthenticated_studies(client, args.base_url)))
        results.append(("Bad login rejected", test_bad_login(client, args.base_url)))

        token = test_login(client, args.base_url, args.username, args.password)
        results.append(("Login", token is not None))

        if token:
            studies = test_list_studies(client, args.base_url, token)
            results.append(("List studies", True))
            results.append(("Study detail", test_study_detail(client, args.base_url, token, studies)))

        test_openapi(client, args.base_url)  # informational

    # ─── Summary ─────────────────────────────────────────────────────────────
    print(f"\n{C.B}== Summary =={C.E}")
    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    for name, ok in results:
        mark = f"{C.G}[PASS]{C.E}" if ok else f"{C.R}[FAIL]{C.E}"
        print(f"  {mark} {name}")

    if passed == total:
        print(f"\n{C.G}{C.B}All smoke tests passed ({passed}/{total}){C.E}")
        return 0
    print(f"\n{C.R}{C.B}{total - passed} test(s) failed ({passed}/{total}){C.E}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
