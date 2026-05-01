# Scripts

Two Python scripts that maintain this repo. No third-party dependencies — standard library only. Tested on Python 3.10+.

## `fetch_exams.py`

Fetches exam problems from the [AoPS wiki](https://artofproblemsolving.com/wiki) and writes them to `problems/<competition>/<year><variant>.md` in this repo's format. Tags are assigned by a keyword-based heuristic (imperfect — review and correct the `*Tags:*` lines after fetching).

```bash
python scripts/fetch_exams.py amc10 --years 2023
python scripts/fetch_exams.py amc10 --years 2022,2023,2024 --variants A
python scripts/fetch_exams.py amc10 --years 2020-2024
python scripts/fetch_exams.py aime  --years 2023
python scripts/fetch_exams.py amc8  --years 2023
```

**Flags:**
- `--years` — comma-separated list of years and/or inclusive ranges (`2020-2024,2022`). Required.
- `--variants` — comma-separated subset of the competition's variants (A/B for AMC 10/12, I/II for AIME). Defaults to all.
- `--overwrite` — replace existing `.md` files. Default: skip files that already exist.

**Rate:** sleeps 0.5s between requests to be polite to AoPS. One AMC exam takes ~13s, one AIME exam takes ~8s.

**Caveats:**
- Asymptote (`<asy>`) diagrams are stripped — they don't render in Markdown. Problems that depend on a diagram will reference the AoPS page.
- Wiki images (`[[Image:...]]`) are stripped for the same reason.
- Tag assignment is a heuristic; audit before trusting topic pages.
- Problem pages that redirect (common for shared problems across AMC 10A/12A) follow the redirect automatically.

## `build_topic_indices.py`

Scans every `.md` under `problems/`, extracts each problem's `*Tags:*` line, and regenerates the tables in `topics/*.md`. Run this after fetching, or any time you edit tags by hand.

```bash
python scripts/build_topic_indices.py
```

The script only replaces the content between `<!-- AUTOGEN-START -->` and `<!-- AUTOGEN-END -->` markers in each topic file — the heading and description are preserved.

If an exam file uses a tag slug that has no corresponding `topics/<slug>.md`, the script creates a stub for it with a warning.

## Typical workflow

```bash
# 1. Fetch a batch of exams
python scripts/fetch_exams.py amc10 --years 2023
python scripts/fetch_exams.py aime  --years 2023

# 2. Open the generated files under problems/ and correct any bad tags
# 3. Rebuild topic indices
python scripts/build_topic_indices.py
```
