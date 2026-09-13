# Oracle_SCM_Quarterly_Update
# Oracle Fusion SCM Quarterly Update Tracker

Fetches Oracle Fusion SCM quarterly feature data (26A, 26B, 26C, 26D, ...)
directly from Oracle's public backend REST API. No browser automation,
no Playwright, no bot-detection risk -- just plain HTTP requests.

## How it works

Oracle's own "Cloud Applications Readiness Reports Center" web app calls
a public JSON API under the hood. `fetch_readiness_api.py` calls that
same API directly:

1. Fetches the full Pillar -> Product -> Module taxonomy to find every
   product/module under the "Supply Chain & Manufacturing (SCM)" pillar.
2. For each product, fetches the list of quarterly releases and their
   internal numeric IDs (e.g. "Update 26D" -> 1373).
3. For each product/module, fetches the complete feature records for the
   quarters you asked for -- full descriptions, business benefits, setup
   steps, everything.

## Setup

```bash
pip install requests
```

## Running it

```bash
# Fetch all SCM features for these quarters in one run
python fetch_readiness_api.py --updates 26A 26B 26C 26D --out ./data

# See what's new since the last saved baseline
python diff_api_results.py --old ./data/scm_features_prev.json \
                            --new ./data/scm_features_api_26A_26B_26C_26D.json \
                            --out ./data/new_features.json
```

## GitHub Actions

`.github/workflows/fetch-oracle-scm.yml` runs this weekly and commits the
results back into the `data/` folder, with a diff step that flags newly
added features since the last run. Trigger it manually from the Actions
tab any time via "Run workflow".

## Extending

- **Non-SCM pillars**: change `SCM_PILLAR_LABEL` in `fetch_readiness_api.py`
  to target a different pillar (e.g. Financials, HCM) the same way.
- **Notifications**: add a step after the diff that reads
  `new_features.json` and posts to Slack/Teams/email.
- **Review tracking**: layer a simple status column (Reviewed / Adopt /
  Ignore) on top of the feature list for your functional leads.
