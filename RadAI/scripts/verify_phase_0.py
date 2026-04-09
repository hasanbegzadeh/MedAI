import time
import httpx
import sys

def verify_system():
    print("--- RadAI Phase 0 Verification ---")
    
    # Check Backend Health (which checks DB, Redis, Ollama)
    # We use -k (verify=False) because we use a self-signed cert
    base_url = "https://localhost"
    print(f"Testing connectivity to {base_url}/health...")
    
    try:
        with httpx.Client(verify=False) as client:
            # 1. Check Gateway
            resp = client.get(f"{base_url}/health", timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                print(f"✅ Gateway & Backend: ONLINE (Status: {data.get('status')})")
                for service, status in data.get("checks", {}).items():
                    if status == "ok":
                        print(f"  - {service}: ✅ OK")
                    else:
                        print(f"  - {service}: ❌ {status}")
            else:
                print(f"❌ Gateway returned status {resp.status_code}")
                
            # 2. Check OHIF
            resp = client.get(base_url, timeout=10)
            if resp.status_code == 200 and "<title>OHIF Viewer</title>" in resp.text:
                print("✅ OHIF Viewer: ACCESSIBLE at https://localhost")
            else:
                print("❌ OHIF Viewer: UNREACHABLE or invalid response")

            # 3. Check Orthanc
            # Use the credentials we generated in .env (I'll just try to reach the login page for now)
            resp = client.get(f"{base_url}/orthanc/app/explorer.html", timeout=10)
            if resp.status_code in [200, 401]:
                print("✅ Orthanc PACS: ACCESSIBLE at https://localhost/orthanc/")
            else:
                print(f"❌ Orthanc PACS: UNREACHABLE (Status {resp.status_code})")

    except Exception as e:
        print(f"FAILED: Verification failed: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    verify_system()
