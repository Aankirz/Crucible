# Crucible data

This directory holds the benchmark databases and gold-question files the loop
evaluates against. **Everything here is gitignored** (large + license-bound) —
download it locally and place files at the paths below so they line up with the
env vars in `.env`.

## Env var ↔ path mapping

The scripts read these env vars (see `.env.example`):

| Env var               | Default path                       | What it points at                          |
| --------------------- | ---------------------------------- | ------------------------------------------ |
| `CRUCIBLE_DB_PATH`    | `data/world_1/world_1.sqlite`      | The live-demo SQLite DB (`world_1`)        |
| `CRUCIBLE_SPIDER_DEV` | `data/spider/dev.json`             | Spider dev gold questions (all DBs)        |

`run_loop_cli.py` uses both. `run_prebaked.py` reuses `CRUCIBLE_SPIDER_DEV` for
its question source and reads each target DB from the hardcoded `TARGETS` paths.

## 1. Download Spider

Spider 1.0: <https://yale-lily.github.io/spider> (Google Drive link on that page).
Unzip it; the archive contains:

- `dev.json` — the dev-split gold questions (`db_id`, `question`, `query`, ...).
- `database/<db_id>/<db_id>.sqlite` — one SQLite file per database.

### Place the files

```text
data/
  spider/
    dev.json                              # from Spider's dev.json
  world_1/
    world_1.sqlite                        # from database/world_1/world_1.sqlite
  concert_singer/
    concert_singer.sqlite                 # from database/concert_singer/concert_singer.sqlite
```

Copy the per-DB `.sqlite` files out of Spider's `database/<db_id>/` folders into
the layout above (matching the `CRUCIBLE_DB_PATH` / `TARGETS` paths). Confirm the
paths match your `.env` before running.

## 2. BIRD financial DB (for the pre-baked generality run)

`run_prebaked.py` also targets a BIRD `financial` database to show the loop
generalizes beyond Spider.

BIRD: <https://bird-bench.github.io> — download the dev set, then place the
`financial` SQLite file at:

```text
data/
  bird/
    financial/
      financial.sqlite                    # from BIRD's financial database
```

BIRD ships its questions in a different JSON shape than Spider. The loader
(`crucible.datasets.spider_loader.load_spider_dev`) expects Spider-style records
with `db_id` / `question` / `query` keys, so either:

- add BIRD's `financial` rows (normalized to those keys, with `db_id="financial"`)
  into your `data/spider/dev.json`, **or**
- point `CRUCIBLE_SPIDER_DEV` at a combined dev file that includes them.

The `db_id` in the questions must equal the `db_id` in `run_prebaked.py`'s
`TARGETS` (`concert_singer`, `financial`) for filtering to return items.

## Generated output

`run_prebaked.py` writes `data/prebaked_results.json`
(`{db_id: {final_test, history}}`) — also gitignored.
