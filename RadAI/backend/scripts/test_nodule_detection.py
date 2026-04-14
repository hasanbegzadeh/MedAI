"""Quick smoke test for nodule detection."""
import sys
sys.path.insert(0, "/app")

import numpy as np
from app.ai.nodule_detection import detect_nodules, NoduleCandidate

# Create synthetic CT: air background with small tissue-density spheres
ct = np.full((64, 64, 64), -1000, dtype=np.float32)
spacing = (1.0, 1.0, 1.0)

# Nodule 1: 5mm sphere at (20, 20, 20), ~40 HU
y, x, z = np.ogrid[:64, :64, :64]
dist1 = np.sqrt((y - 20) ** 2 + (x - 20) ** 2 + (z - 20) ** 2)
ct[dist1 <= 2.5] = 40

# Nodule 2: 8mm sphere at (40, 40, 40), ~30 HU
dist2 = np.sqrt((y - 40) ** 2 + (x - 40) ** 2 + (z - 40) ** 2)
ct[dist2 <= 4.0] = 30

# Nodule 3: 3mm sphere at (30, 50, 30), ~50 HU
dist3 = np.sqrt((y - 30) ** 2 + (x - 50) ** 2 + (z - 30) ** 2)
ct[dist3 <= 1.5] = 50

# Lung mask: entire volume
lung_mask = np.ones((64, 64, 64), dtype=np.int32)

candidates = detect_nodules(ct, lung_mask, spacing)
print(f"Found {len(candidates)} nodule candidates")
for c in candidates:
    print(f"  {c.nodule_id}: d={c.diameter_mm}mm, HU={c.mean_hu:.0f}, {c.location}, conf={c.confidence}")

assert len(candidates) >= 2, f"Expected at least 2 candidates, got {len(candidates)}"
print("\nNodule detection smoke test PASSED")
