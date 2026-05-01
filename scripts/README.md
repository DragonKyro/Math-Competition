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
- `--variants` — comma-separated subset of variants. Defaults:
  - AMC 8: `""` (no variants)
  - AMC 10 / AMC 12: `"", "A", "B"` (empty is for pre-2002 when the split didn't exist yet)
  - AIME: `"", "I", "II"` (empty is for pre-2000 when there was one AIME)
  - Pass `--variants A,B` to narrow (skips the empty-variant probe).
- `--overwrite` — replace existing `.md` files. Default: skip files that already exist.

**Skip behavior:** before fetching all 25 (or 15) problems for an exam, the script probes Problem 1. If that page doesn't exist on AoPS, the exam is skipped and no file is written. This makes it safe to run over wide year ranges — e.g. `--years 1985-2024` on AMC 10 — and only get files for exams that actually exist.

**Rate:** sleeps 0.5s between requests to be polite to AoPS. One AMC exam takes ~13s, one AIME exam takes ~8s. A full fetch across every AMC 8/10/12/AIME exam takes ~35–40 min.

**Caveats:**
- Asymptote (`<asy>`) diagrams are stripped — they don't render in Markdown. Problems that depend on a diagram will reference the AoPS page.
- Wiki images (`[[Image:...]]`) are stripped for the same reason.
- Tag assignment is a heuristic; audit before trusting topic pages.
- Problem pages that redirect (common for shared problems across AMC 10A/12A) follow the redirect automatically.

## `retag.py`

Replaces each problem's `*Tags:*` line with narrow technique tags (e.g. `vietas-formulas`, `power-of-a-point`, `law-of-cosines`) derived from pattern-matching the problem's solution text. Falls back to broad-area tags (`algebra`, `geometry`, `number-theory`, etc.) when no narrow technique is detected.

```bash
python scripts/retag.py                    # retag every problem under problems/
python scripts/retag.py problems/aime      # retag one subdirectory
python scripts/retag.py --dry-run          # show tag counts without writing
```

**How it works:** `TAG_PATTERNS` in [retag.py](retag.py) maps each tag slug to a list of regexes. For every problem, the script scans both the problem statement and all solutions; any pattern that matches contributes its tag. When the narrow set is empty, `fetch_exams.guess_tags` runs on the problem text as a fallback.

**Tuning the tag list:** add/remove entries in `TAG_PATTERNS`, then rerun. Regexes are case-insensitive. Prefer phrases authors actually write (`by Vieta's`, `applying the law of cosines`, `case 1:`) over mathematical notation alone.

**After running,** rebuild topic pages:

```bash
python scripts/build_topic_indices.py
```

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

# 2. Retag based on solution text (narrow technique tags instead of broad areas)
python scripts/retag.py problems/amc10 problems/aime

# 3. Open the generated files and correct any bad tags
# 4. Rebuild topic indices
python scripts/build_topic_indices.py
```

## Fetching every exam in one go

```bash
python scripts/fetch_exams.py amc8  --years 1985-2024
python scripts/fetch_exams.py amc10 --years 2000-2024
python scripts/fetch_exams.py amc12 --years 2000-2024
python scripts/fetch_exams.py aime  --years 1983-2024
python scripts/build_topic_indices.py
```

Non-existent year/variant combinations (e.g. `1985_AMC_10A`, `2023_AIME` without I/II) are skipped automatically.
