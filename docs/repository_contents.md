# What is in this repository, and what is not

A reader should be able to see the whole result without running anything, and
reproduce it from scratch if they want to. That means the code, the documents
and the figures are tracked, while the source data and everything derived from
it are not.

## Tracked

| Path | What it is | Why it is here |
| --- | --- | --- |
| `src/` | Ingest, transform, quality checks, KPIs, insights, charts | The work itself |
| `sql/` | Star schema DDL and a preview query | The model, readable without running it |
| `docs/` | Schema contract, metric definitions, column dictionary, AWS setup, findings | The reasoning behind the code |
| `output/fig_*.png` | Six exploration charts | So the findings are visible in the browser |
| `output/*.json` | `insights.json`, `kpi_summary.json` | The numbers the write-up quotes, in machine-readable form |
| `explore_raw_data.ipynb` | First-pass look at the nine raw tables | Where the project started. Outputs stripped |
| `requirements.txt` | Pinned dependencies | |
| `.env.example` | Variable names only, no values | Shows what an S3 run needs |

## Not tracked

| Path | Size | Why not |
| --- | --- | --- |
| `data/` | ~120 MB | Public Kaggle dataset. Redistributing it adds nothing and makes the clone slow. The README links it |
| `lake/` | ~187 MB | Entirely derived. One command rebuilds it from `data/` |
| `.venv/` | ~390 MB | Local environment |
| `.env` | — | Real credentials. Only `.env.example` is tracked |
| `.vscode/`, `.mplconfig/`, `.DS_Store` | small | Local editor and OS artifacts |

## Checks run before publishing

| Check | Result |
| --- | --- |
| Any non-English text in tracked files | None. The one Chinese setup note in the notebook was translated |
| Any credential, key, bucket name or account id | None. `.env.example` holds placeholder names only |
| Any file over 50 MB | None once `data/` and `lake/` are excluded |
| Notebook execution outputs | Stripped, so diffs stay readable |
| Absolute paths from the author's machine | None. Every path is relative to the project root |

## Reproducing it

```bash
pip install -r requirements.txt
# download the nine CSVs into data/ from the Kaggle link in the README
python -m src.run_pipeline --skip-s3   # data/ -> lake/raw -> star schema -> quality checks
python -m src.report_kpis              # KPI summary and charts
python -m src.run_insights             # findings -> output/insights.json
python -m src.plot_insights            # charts   -> output/fig_*.png
```

The figures already in `output/` were produced by exactly these commands, so a
rerun should reproduce them.
