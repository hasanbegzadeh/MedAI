"""Debug Lung-RADS template."""
import sys
sys.path.insert(0, "/app")

from app.reporting.engine import get_template_engine, build_lung_rads_context

engine = get_template_engine()
ctx = build_lung_rads_context(findings=[], lung_rads_category="Lung-RADS 3")
report = engine.render("lung_rads.j2", ctx)

print("HAS CATEGORY:", "Lung-RADS 3" in report)
print("LENGTH:", len(report))

idx = report.find("IMPRESSION")
if idx >= 0:
    print("\nIMPRESSION SECTION:")
    print(report[idx:idx+300])
else:
    print("\nNO IMPRESSION SECTION FOUND")

# Print full report for debugging
print("\n=== FULL REPORT ===")
print(report)
