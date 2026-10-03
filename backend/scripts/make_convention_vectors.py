"""Regenerate contracts/conventions_vectors.json from the Python implementation.

The backend and the browser are both tested against this file, so they cannot
drift apart. Run only when the conventions change on purpose:

    uv run python scripts/make_convention_vectors.py
"""

import json

from app.config import REPO_ROOT
from app.core.conventions import LocalFrame, heading_diff

ORIGIN = (12.9716, 77.5946, 900.0)
POINTS = [
    (12.9716, 77.5946, 900.0),
    (12.9720, 77.5946, 900.0),
    (12.9716, 77.5952, 900.0),
    (12.9725, 77.5958, 925.0),
    (12.9701, 77.5931, 902.5),
    (12.9760, 77.6000, 1020.0),
]
HEADINGS = [(10, 350), (350, 10), (180, 0), (0, 180), (90, 90), (271, 90), (45, 405)]

frame = LocalFrame(*ORIGIN)
out = {
    "origin": list(ORIGIN),
    "enu": [{"geodetic": list(p), "enu": [round(v, 6) for v in frame.to_enu(*p)]} for p in POINTS],
    "heading_diff": [{"target": t, "current": c, "diff": heading_diff(t, c)} for t, c in HEADINGS],
}
path = REPO_ROOT / "contracts" / "conventions_vectors.json"
path.parent.mkdir(exist_ok=True)
path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8", newline="\n")
print(f"wrote {path}")
