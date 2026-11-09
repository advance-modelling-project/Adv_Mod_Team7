# ORBIT — Team 7 Simulation Control Room

A static, mobile-friendly back office for the AMFO closed-loop supply-chain model. It **replays real daily Excel snapshots** and renders Markdown reports already committed under `analysis/reports/`. No backend/database/API key is required.

## What it includes

- **Overview:** validated KPIs, source metadata, inventory history.
- **Simulation replay:** animated forward/reverse network, day scrubber, play/pause/speed controls, daily flow bars, screening and overdue quantities. Animation represents **daily aggregates**, not exact RTI trajectories or transport time.
- **Scenario lab:** side-by-side baseline vs RFID KPIs, detention and circulation indicators and interactive time-series overlays. Missing metrics display `—`, never fabricated zeros.
- **Report library:** all `analysis/reports/**/*.md`, sanitized and rendered as Markdown with source/copy controls. New report files appear on the next successful deployment.
- **Automatic builds:** a GitHub Actions workflow validates the code, runs the scenarios supported by the **merged** `main.py`, builds the snapshot JSON, and deploys GitHub Pages after every push to `main` or manual `workflow_dispatch`.

## Publish it

1. Merge the dashboard PR into `main` (with team review).
2. Repository **Settings → Pages → Build and deployment → Source → GitHub Actions**. Repository admin permissions may be needed.
3. Repository **Actions → Publish Team 7 Control Room → Run workflow** to deploy immediately. Later pushes/merges to `main` trigger a new build automatically.
4. Pages URL: `https://ylhhh4.github.io/Adv_Mod_Team7/` after successful deployment.

For now, the merged `main.py` has no `--scenario` switch, so the workflow runs one baseline. When the team's Task 1 traceability code **is merged**, the same workflow automatically runs both `baseline` and `traceability` using seed 42. Avoid merging unfinished RFID policies just to populate the website.

### Local preview with existing workbooks

```powershell
python -m pip install -r requirements.txt mistune bleach
python dashboard/build_data.py --runs-root . --reports analysis/reports --output dashboard/dist
python -m http.server 8000 -d dashboard/dist
```

Then visit `http://localhost:8000/` (not `file:///...`).

### Local tests

```powershell
python -m unittest discover -s dashboard -p "test_*.py" -v
node --check dashboard/site/app.js
```

## Data provenance and limitations

- Each run is derived from a real `sim_log_*.xlsx` workbook: `Stock`, `Flows`, `Backorders`, and optional `Screening`, `Fulfillment`, `Detention` sheets.
- The workflow only publishes after GitHub Actions finishes running. **GitHub Pages is static; it cannot stream Python execution live.** The replay represents the latest successful published build.
- The browser checks for a new bundle every 60 seconds (and when refocused), so a newly deployed build appears without manual refresh.
- Source `run_*` folders are intentionally ignored by Git. Actions generates runs afresh, and the `data/site.json` produced at deploy time is packed into the Pages artifact rather than committed to `main`.
- Snapshot inventory omits in-transit crate counts. Daily flow particles are symbolic and not per-RTI tracking.
- Detention averages are conditional on completed departures; right-censored crates still in the network at day 365 are excluded.
- A matched seed does not guarantee shared random-number streams if policies change RNG call patterns. Use replications/ANOVA for claims about scenario value.
- Larger future deployments: store replication summaries or experiment tables separately; avoid trying to render 322,800 agent records in the browser.
