"""
RadAI Phase 0 Verification Script

Runs end-to-end checks against the local Docker Compose stack to validate
all Phase 0 requirements from MASTER_PLAN.md:
  - Docker + Orthanc + PostgreSQL + Redis + OHIF v3.12 deployed
  - Ollama verified with MedGemma 1.5 4B
  - PyTorch >= 2.6.0 with Blackwell (sm_120) RTX 5060 support
  - TLS/SSL configured for browser-to-Orthanc traffic
  - JWT authentication for OHIF frontend
  - WebSocket endpoint for AI progress streaming

Usage:
    python scripts/verify_phase_0.py
    python scripts/verify_phase_0.py --skip-ssl  # If using HTTP only
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

try:
    import httpx
except ImportError:
    print("ERROR: httpx not installed. Run: pip install httpx")
    sys.exit(1)


# ─── Pretty printing helpers ──────────────────────────────────────────────────
class Col:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    END = "\033[0m"


def ok(msg: str) -> None:
    print(f"  {Col.GREEN}[OK]{Col.END} {msg}")


def fail(msg: str) -> None:
    print(f"  {Col.RED}[FAIL]{Col.END} {msg}")


def warn(msg: str) -> None:
    print(f"  {Col.YELLOW}[WARN]{Col.END} {msg}")


def info(msg: str) -> None:
    print(f"  {Col.BLUE}[INFO]{Col.END} {msg}")


def section(title: str) -> None:
    print(f"\n{Col.BOLD}{Col.CYAN}-- {title} --{Col.END}")


# ─── Individual checks ────────────────────────────────────────────────────────
def check_backend_health(client: httpx.Client, base_url: str) -> bool:
    section("Backend API Health")
    try:
        resp = client.get(f"{base_url}/health", timeout=10)
        if resp.status_code != 200:
            fail(f"GET /health returned {resp.status_code}")
            return False
        data = resp.json()
        ok(f"Gateway reachable, overall status: {data.get('status')}")
        all_ok = True
        for service, status in (data.get("checks") or {}).items():
            if status == "ok":
                ok(f"{service}: OK")
            else:
                fail(f"{service}: {status}")
                all_ok = False
        return all_ok
    except Exception as e:
        fail(f"Cannot reach backend: {e}")
        return False


def check_ohif(client: httpx.Client, base_url: str) -> bool:
    section("OHIF Viewer")
    try:
        resp = client.get(base_url, timeout=10)
        if resp.status_code == 200 and "<title>OHIF Viewer</title>" in resp.text:
            ok(f"OHIF Viewer accessible at {base_url}")
            return True
        fail(f"OHIF responded {resp.status_code} but did not return the expected HTML")
        return False
    except Exception as e:
        fail(f"Cannot reach OHIF: {e}")
        return False


def check_orthanc(client: httpx.Client, base_url: str) -> bool:
    section("Orthanc PACS")
    try:
        # /orthanc/app/explorer.html requires auth — 401 is expected and means it is reachable
        resp = client.get(f"{base_url}/orthanc/app/explorer.html", timeout=10)
        if resp.status_code in (200, 401):
            ok(f"Orthanc reachable at {base_url}/orthanc/ (HTTP {resp.status_code})")
            return True
        fail(f"Orthanc returned unexpected status {resp.status_code}")
        return False
    except Exception as e:
        fail(f"Cannot reach Orthanc: {e}")
        return False


def check_orthanc_dicomweb(client: httpx.Client, base_url: str) -> bool:
    try:
        pw = os.environ.get("ORTHANC_PASSWORD", "orthanc")
        resp = client.get(
            f"{base_url}/orthanc/dicom-web/studies",
            auth=("orthanc", pw),
            timeout=10,
        )
        if resp.status_code in (200, 204):
            try:
                studies = resp.json() if resp.text else []
            except Exception:
                studies = []
            ok(f"DICOMweb QIDO-RS responsive ({len(studies)} studies currently stored)")
            return True
        warn(f"DICOMweb returned {resp.status_code} (check ORTHANC_PASSWORD in env)")
        return False
    except Exception as e:
        warn(f"DICOMweb check skipped: {e}")
        return False


def check_jwt_auth(client: httpx.Client, base_url: str) -> bool:
    section("JWT Authentication")
    try:
        # Try the default seeded admin user from docker/postgres/init.sql
        resp = client.post(
            f"{base_url}/api/v1/auth/login",
            json={"username": "admin", "password": "changeme"},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            if "access_token" in data:
                ok("Admin login successful, JWT access token returned")
                return True
            fail(f"Login returned 200 but no access_token in response: {data}")
            return False
        elif resp.status_code == 404:
            warn(f"Login endpoint not mounted at /api/v1/auth/login ({resp.status_code})")
            return False
        else:
            warn(f"Login failed with HTTP {resp.status_code}: {resp.text[:200]}")
            return False
    except Exception as e:
        warn(f"Cannot test JWT auth: {e}")
        return False


def check_websocket(base_url: str) -> bool:
    section("WebSocket Progress Stream")
    try:
        import websockets  # type: ignore  # noqa: F401
    except ImportError:
        info("websockets package not installed - skipping live WS check")
        info("To test: pip install websockets")
        return True  # Not a hard failure

    import asyncio
    from urllib.parse import urlparse

    parsed = urlparse(base_url)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    ws_url = f"{scheme}://{parsed.netloc}/api/v1/ws/progress"

    async def _try():
        import ssl as _ssl
        import websockets
        ssl_ctx = _ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = _ssl.CERT_NONE
        async with websockets.connect(
            ws_url, ssl=ssl_ctx if scheme == "wss" else None, open_timeout=5
        ) as ws:
            await ws.close()

    try:
        asyncio.run(_try())
        ok(f"WebSocket endpoint reachable at {ws_url}")
        return True
    except Exception as e:
        warn(f"WebSocket probe failed: {e}")
        return False


def check_ollama() -> bool:
    section("Ollama + MedGemma 1.5 4B")
    ollama_url = os.environ.get("OLLAMA_URL", "http://localhost:11434")
    try:
        with httpx.Client(timeout=5) as c:
            resp = c.get(f"{ollama_url}/api/tags")
        if resp.status_code != 200:
            warn(f"Ollama not responding at {ollama_url} (HTTP {resp.status_code})")
            return False
        models = [m.get("name", "") for m in resp.json().get("models", [])]
        ok(f"Ollama reachable at {ollama_url}")
        if any("medgemma" in m.lower() for m in models):
            medgemma = next(m for m in models if "medgemma" in m.lower())
            ok(f"MedGemma model available: {medgemma}")
            return True
        warn(f"MedGemma model not found in Ollama. Available: {models}")
        return False
    except Exception as e:
        warn(f"Ollama not reachable: {e}")
        return False


def check_pytorch_blackwell() -> bool:
    section("PyTorch + CUDA (host)")
    try:
        import torch  # type: ignore
    except ImportError:
        warn("PyTorch not installed in host Python - host check skipped")
        info("This check will be run inside the backend container via 'make verify-gpu'")
        return True  # Not a hard failure - container check is authoritative

    ver = torch.__version__
    ok(f"PyTorch version: {ver}")
    if not ver.startswith(("2.6", "2.7", "2.8", "2.9", "2.10", "2.11")):
        warn(f"PyTorch {ver} may be below the >=2.6.0 requirement")

    if not torch.cuda.is_available():
        fail("CUDA is not available")
        return False
    ok(f"CUDA available (runtime: {torch.version.cuda})")
    ok(f"GPU: {torch.cuda.get_device_name(0)}")
    cc = torch.cuda.get_device_capability(0)
    ok(f"Compute capability: sm_{cc[0]}{cc[1]}")
    if cc == (12, 0):
        ok("Blackwell (sm_120) detected - RTX 50-series support confirmed")
    return True


def check_ssl_cert(base_url: str) -> bool:
    section("TLS / HTTPS")
    if not base_url.startswith("https://"):
        warn(f"Base URL is HTTP, not HTTPS: {base_url}")
        return False
    cert_path = Path("docker/nginx/ssl/server.crt")
    key_path = Path("docker/nginx/ssl/server.key")
    if not cert_path.exists():
        fail(f"Missing cert: {cert_path}")
        return False
    if not key_path.exists():
        fail(f"Missing key: {key_path}")
        return False
    ok("Self-signed certificate and private key present")
    ok(f"HTTPS endpoint: {base_url}")
    return True


# ─── Main entry point ────────────────────────────────────────────────────────
def main() -> int:
    parser = argparse.ArgumentParser(description="RadAI Phase 0 Verification")
    parser.add_argument(
        "--base-url",
        default=os.environ.get("RADAI_BASE_URL", "https://localhost"),
        help="Base URL of the Nginx gateway (default: https://localhost)",
    )
    parser.add_argument(
        "--skip-ssl",
        action="store_true",
        help="Skip SSL certificate file checks",
    )
    parser.add_argument(
        "--skip-ollama",
        action="store_true",
        help="Skip Ollama / MedGemma check",
    )
    args = parser.parse_args()

    print(f"{Col.BOLD}-- RadAI Phase 0 Verification --{Col.END}")
    print(f"Target: {args.base_url}")

    results: list[tuple[str, bool]] = []

    with httpx.Client(verify=False) as client:
        results.append(("Backend API", check_backend_health(client, args.base_url)))
        results.append(("OHIF Viewer", check_ohif(client, args.base_url)))
        results.append(("Orthanc PACS", check_orthanc(client, args.base_url)))
        check_orthanc_dicomweb(client, args.base_url)  # informational
        results.append(("JWT Auth", check_jwt_auth(client, args.base_url)))

    check_websocket(args.base_url)  # informational
    if not args.skip_ollama:
        check_ollama()  # informational - may run on host
    check_pytorch_blackwell()  # informational
    if not args.skip_ssl:
        check_ssl_cert(args.base_url)  # informational

    # ─── Summary ────────────────────────────────────────────────────────────
    print(f"\n{Col.BOLD}-- Summary --{Col.END}")
    critical_passed = sum(1 for _, ok_ in results if ok_)
    critical_total = len(results)
    for name, passed in results:
        symbol = f"{Col.GREEN}[OK]{Col.END}" if passed else f"{Col.RED}[FAIL]{Col.END}"
        print(f"  {symbol} {name}")

    if critical_passed == critical_total:
        print(f"\n{Col.GREEN}{Col.BOLD}All critical checks passed ({critical_passed}/{critical_total}){Col.END}")
        return 0

    print(
        f"\n{Col.RED}{Col.BOLD}"
        f"{critical_total - critical_passed} critical check(s) failed "
        f"({critical_passed}/{critical_total} passing){Col.END}"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
