"""
diff_api_results.py

Compares two runs of fetch_readiness_api.py output (each a flat JSON list
of feature records) and reports which FEATURE_IDs are new in the later
run. Use this to route only genuinely new features to reviewers each
time the workflow runs, instead of re-reviewing everything.

USAGE:
    python diff_api_results.py --old ./data/scm_features_prev.json \
                                --new ./data/scm_features_api_26A_26B_26C_26D.json \
                                --out ./data/new_features.json
"""

import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--old", required=True)
    parser.add_argument("--new", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    old_path = Path(args.old)
    new_path = Path(args.new)

    new_features = json.loads(new_path.read_text())

    if old_path.exists():
        old_features = json.loads(old_path.read_text())
        old_ids = {f.get("FEATURE_ID") for f in old_features}
    else:
        old_ids = set()  # first run ever -- everything counts as "new"

    added = [f for f in new_features if f.get("FEATURE_ID") not in old_ids]

    Path(args.out).write_text(json.dumps(added, indent=2))
    print(f"{len(added)} new features (out of {len(new_features)} total) -> {args.out}")


if __name__ == "__main__":
    main()
