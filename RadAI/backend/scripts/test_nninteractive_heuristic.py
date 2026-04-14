"""Smoke test for nnInteractive heuristic refinement."""
import sys
sys.path.insert(0, "/app")

import numpy as np
from app.ai.nninteractive import _heuristic_refine

# Create synthetic CT volume (32x64x64)
ct = np.full((32, 64, 64), -1000, dtype=np.float32)  # Air background

# Add a soft-tissue region (~50 HU) at slice 16, center
ct[15:19, 20:44, 20:44] = 50

# Click in the center of the tissue
clicks = [
    {"type": "positive", "x": 32, "y": 32, "slice_index": 16},
]

mask = _heuristic_refine(ct, clicks)

total_voxels = int(np.sum(mask))
print(f"Heuristic refinement: {total_voxels} voxels segmented")

assert total_voxels > 0, "Expected non-zero mask from click"
assert mask.shape == ct.shape, f"Mask shape {mask.shape} != CT shape {ct.shape}"
assert mask.dtype == np.uint8, f"Mask dtype {mask.dtype} != uint8"

# Click should have grown into the tissue region
# The tissue region is 4 slices * 24x24 = 2304 voxels
# Heuristic dilation + fill should capture a significant portion
print(f"Coverage: {total_voxels}/{2304} tissue voxels ({100*total_voxels/2304:.0f}%)")
assert total_voxels > 100, f"Expected at least 100 voxels, got {total_voxels}"

print("\nnnInteractive heuristic smoke test PASSED")
