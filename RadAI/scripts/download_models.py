#!/usr/bin/env python3
"""Download and cache AI model checkpoints required by RadAI.

Run this script before starting the stack to ensure all required
model weights are present locally.  Models that are already present
are skipped.

Usage:
    python scripts/download_models.py              # download all
    python scripts/download_models.py --lite-medsam  # download only LiteMedSAM
    python scripts/download_models.py --list         # list available models
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import urllib.request
from pathlib import Path
from typing import NamedTuple

# ─── Model registry ───────────────────────────────────────────────────────────

class ModelEntry(NamedTuple):
    name: str
    filename: str
    url: str
    size_mb: float
    sha256: str | None = None  # optional checksum
    description: str


MODELS: list[ModelEntry] = [
    ModelEntry(
        name="lite-medsam",
        filename="lite_medsam.pth",
        url="https://drive.google.com/uc?export=download&id=18Zed-TUTsmr2zc5CHUWd5Tu13nb6vq6z",
        size_mb=120.0,
        description="LiteMedSAM checkpoint for fast segmentation (~2-3 GB VRAM)",
    ),
]


def models_dir() -> Path:
    """Resolve the models directory from env or default to ./backend/models."""
    import os
    return Path(os.getenv("MODELS_DIR", Path(__file__).resolve().parent.parent / "backend" / "models"))


def download_model(model: ModelEntry, dest: Path, dry_run: bool = False) -> bool:
    """Download a single model checkpoint. Returns True on success."""
    target = dest / model.filename

    if target.exists():
        size_mb = target.stat().st_size / (1024 * 1024)
        print(f"  [SKIP] {model.name} already exists ({size_mb:.1f} MB)")
        return True

    if dry_run:
        print(f"  [DRY-RUN] Would download {model.name} ({model.size_mb:.0f} MB)")
        return True

    print(f"  [DOWNLOAD] {model.name} ({model.size_mb:.0f} MB) …")
    try:
        # Use urllib with a user-agent to avoid some download blockers
        req = urllib.request.Request(model.url, headers={"User-Agent": "RadAI/1.0"})
        with urllib.request.urlopen(req, timeout=600) as resp:
            data = resp.read()

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

        actual_mb = len(data) / (1024 * 1024)
        print(f"  [OK] {model.name} saved ({actual_mb:.1f} MB)")
        return True

    except Exception as exc:
        print(f"  [ERROR] {model.name} failed: {exc}", file=sys.stderr)
        return False


def list_models() -> None:
    """Print available models."""
    print("Available model checkpoints:")
    for m in MODELS:
        print(f"  • {m.name:20s}  {m.filename:25s}  {m.size_mb:6.0f} MB  —  {m.description}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Download AI model checkpoints")
    parser.add_argument("--list", action="store_true", help="List available models")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be downloaded")
    parser.add_argument("--lite-medsam", action="store_true", help="Download only LiteMedSAM")
    args = parser.parse_args()

    dest = models_dir()

    if args.list:
        list_models()
        return 0

    if args.lite_medsam:
        targets = [m for m in MODELS if m.name == "lite-medsam"]
    else:
        targets = MODELS

    print(f"Models directory: {dest.resolve()}")
    all_ok = True
    for model in targets:
        ok = download_model(model, dest, dry_run=args.dry_run)
        all_ok = all_ok and ok

    if not all_ok:
        print("\n⚠  Some downloads failed. Check network / disk space.")
        return 1

    if targets:
        print("\n✓ All model downloads complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
