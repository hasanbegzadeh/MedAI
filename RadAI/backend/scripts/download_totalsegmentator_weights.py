#!/usr/bin/env python3
"""Pre-download TotalSegmentator weights inside the container."""
import subprocess
import sys

print("Pre-downloading TotalSegmentator weights...")
print("This may take a few minutes depending on internet speed.")

# Run TotalSegmentator with --help to trigger weight download
# The fast model weights are downloaded on first import/run
try:
    result = subprocess.run(
        ["TotalSegmentator", "--version"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    print(f"TotalSegmentator version: {result.stdout.strip()}")
except Exception as e:
    print(f"TotalSegmentator check: {e}")

# Try to trigger weight download by running with a dummy input
# The weights are downloaded on first subprocess.run call
print("\nTriggering weight download (will fail on missing input but download weights)...")
result = subprocess.run(
    ["TotalSegmentator", "-i", "/dev/null", "-o", "/tmp/dummy", "-d", "cpu", "--fast"],
    capture_output=True,
    text=True,
    timeout=120,
)

# Check if weights were downloaded
import os
weights_dir = os.path.expanduser("~/.totalsegmentator")
if os.path.exists(weights_dir):
    print(f"\nWeights directory exists: {weights_dir}")
    for root, dirs, files in os.walk(weights_dir):
        for f in files[:10]:  # Show first 10 files
            print(f"  {os.path.join(root, f)}")
    print("\nWeight download complete (or already present)")
else:
    print("\nWARNING: Weights may not have been downloaded")
    print("Check the error output above")
