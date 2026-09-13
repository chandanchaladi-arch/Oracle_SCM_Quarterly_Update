"""
fetch_readiness_api.py

Fetches Oracle Fusion SCM quarterly feature data directly from Oracle's
public backend REST API (Oracle APEX/ORDS) -- no browser, no Playwright,
no bot-detection risk.

HOW THIS WORKS (discovered by inspecting the Reports Center app's own
network traffic):

1. GET https://apexapps.oracle.com/pls/apex/readiness/rsb/service_document/?NAME=dataTree2
   Returns the full Pillar -> Product -> Module taxonomy with internal IDs.
   e.g. "Supply Chain & Manufacturing (SCM)" = pillar value "1"
        "Order Management" product under it  = value "1_157"  (product_id=157)
        "Order Management" module under that = value "1_157-1" (module_id=1)

2. GET https://apexapps.oracle.com/pls/apex/readiness/readiness/release/?N_PRODUCT_IDS={product_id}
   Returns every quarterly release for that product with its internal
   RELEASE_ID, e.g. "Update 26D" -> 1373, "Update 26C" -> 1372.

3. GET https://apexapps.oracle.com/pls/apex/readiness/readiness/feature/
        ?N_PRODUCT_IDS={product_id}&N_MODULE_IDS={module_id}&N_RELEASE_IDS={release_id(s)}
   Returns the COMPLETE feature records for that product/module/release
   (or comma-separated list of releases) -- full descriptions, business
   benefits, setup steps, everything. This is the real target data.

SETUP:
    pip install requests --break-system-packages

USAGE:
    python fetch_readiness_api.py --updates 26A 26B 26C 26D --out ./data
"""

import argparse
import json
import re
import time
from pathlib import Path

import requests

DATATREE_URL = "https://apexapps.oracle.com/pls/apex/readiness/rsb/service_document/?NAME=dataTree2"
RELEASE_URL = "https://apexapps.oracle.com/pls/apex/readiness/readiness/release/"
FEATURE_URL = "https://apexapps.oracle.com/pls/apex/readiness/readiness/feature/"

SCM_PILLAR_LABEL = "Supply Chain & Manufacturing (SCM)"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (internal release-tracking tool; contact: you@yourcompany.com)"
}


def strip_html(html: str) -> str:
    """Rough HTML-to-text conversion for the description fields, which
    come back as raw HTML from the API."""
    if not html:
        return ""
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def get_scm_products_and_modules() -> list[dict]:
    """Fetch the full taxonomy and return every (product_id, module_id)
    pair under the SCM pillar, with human-readable names."""
    resp = requests.get(DATATREE_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    payload = resp.json()
    tree = json.loads(payload["items"][0]["data"])["tree"]

    scm_node = next((n for n in tree if n["label"] == SCM_PILLAR_LABEL), None)
    if not scm_node:
        raise RuntimeError(f"Could not find pillar '{SCM_PILLAR_LABEL}' in taxonomy")

    results = []
    for product in scm_node["children"]:
        # product["value"] looks like "1_157"
        product_id = int(product["value"].split("_")[1])
        product_name = product["label"]
        for module in product.get("children") or []:
            # module["value"] looks like "1_157-1"
            module_id = int(module["value"].split("-")[1])
            results.append({
                "product_id": product_id,
                "product_name": product_name,
                "module_id": module_id,
                "module_name": module["label"],
            })
    return results


def get_release_id_map(product_id: int) -> dict:
    """Fetch the release list for a product and return {release_name: release_id}."""
    resp = requests.get(RELEASE_URL, headers=HEADERS,
                         params={"N_PRODUCT_IDS": product_id}, timeout=30)
    resp.raise_for_status()
    items = resp.json().get("ITEMS", [])
    return {item["RELEASE_NAME"]: item["RELEASE_ID"] for item in items}


def get_features(product_id: int, module_id: int, release_ids: list[int]) -> list[dict]:
    """Fetch feature records for a product/module across one or more releases."""
    release_ids_csv = ",".join(str(r) for r in release_ids)
    resp = requests.get(
        FEATURE_URL, headers=HEADERS,
        params={
            "N_PRODUCT_IDS": product_id,
            "N_MODULE_IDS": module_id,
            "N_RELEASE_IDS": release_ids_csv,
        },
        timeout=30,
    )
    if resp.status_code != 200:
        print(f"    HTTP {resp.status_code} for product={product_id} module={module_id}")
        return []
    data = resp.json()
    # The API wraps results in a nested list: [[ {...}, {...} ]]
    if isinstance(data, list) and data and isinstance(data[0], list):
        return data[0]
    return data if isinstance(data, list) else []


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--updates", nargs="+", required=True,
                         help="e.g. 26A 26B 26C 26D")
    parser.add_argument("--out", default="./data")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    target_release_names = {f"Update {u.upper()}" for u in args.updates}

    print("Fetching SCM product/module taxonomy...")
    products_modules = get_scm_products_and_modules()
    print(f"Found {len(products_modules)} product/module combinations under SCM.")

    # Cache release-id maps per product so we don't refetch per module.
    release_map_cache: dict[int, dict] = {}

    all_features = []
    for pm in products_modules:
        product_id = pm["product_id"]

        if product_id not in release_map_cache:
            try:
                release_map_cache[product_id] = get_release_id_map(product_id)
            except Exception as e:
                print(f"  Failed to fetch releases for product {product_id} ({pm['product_name']}): {e}")
                release_map_cache[product_id] = {}
            time.sleep(0.5)  # be polite

        release_map = release_map_cache[product_id]
        matching_release_ids = [
            release_map[name] for name in target_release_names if name in release_map
        ]
        if not matching_release_ids:
            continue  # this product doesn't have data for the requested quarters

        print(f"  {pm['product_name']} / {pm['module_name']} "
              f"(product={product_id}, module={pm['module_id']})...")
        features = get_features(product_id, pm["module_id"], matching_release_ids)
        for f in features:
            f["_product_name"] = pm["product_name"]
            f["_module_name"] = pm["module_name"]
            f["SHORT_DESCRIPTION_TEXT"] = strip_html(f.get("SHORT_DESCRIPTION", ""))
        all_features.extend(features)
        time.sleep(0.3)  # be polite between calls

    # De-duplicate by FEATURE_ID (a feature can appear once per matched release
    # already, but guard against any accidental overlap).
    seen_ids = set()
    deduped = []
    for f in all_features:
        fid = f.get("FEATURE_ID")
        if fid in seen_ids:
            continue
        seen_ids.add(fid)
        deduped.append(f)

    update_tag = "_".join(sorted(u.upper() for u in args.updates))
    out_path = out_dir / f"scm_features_api_{update_tag}.json"
    out_path.write_text(json.dumps(deduped, indent=2))
    print(f"\nSaved {len(deduped)} features across {len(products_modules)} "
          f"product/module combos to {out_path}")


if __name__ == "__main__":
    main()
