# CLAUDE.md

Conventions for this repo. Read this before adding exams, changing formats, or extending the scripts.

## What this repo is

A personal library of math-competition problems and solutions (AMC 8/10/12, AIME, extendable), organized so problems can be practiced **by exam** or **by topic**. Each problem lives in exactly one file (its exam file); topic pages are generated indexes that link into those files via heading anchors.

## Non-negotiables

- **One problem lives in exactly one place** — inside its exam `.md` under `problems/<competition>/<file>`. Never duplicate problems into a `solutions/` tree or a `topics/` tree.
- **Solutions go inside `<details><summary>Solution</summary> ... </details>`** so readers can attempt the problem without spoilers.
- **Topic pages are generated, not hand-edited.** Only the content between `<!-- AUTOGEN-START -->` and `<!-- AUTOGEN-END -->` is rewritten; the heading and description above those markers are preserved. Never paste a table outside that block.

## Exam file format

```markdown
# 2023 AIME I

## Problem 1
*Tags: probability, combinatorics*

Problem statement with $\LaTeX$ math in dollar signs.

<details><summary>Solution</summary>

**Solution 1.**

Full walkthrough.

**Answer:** $\boxed{191}$

</details>

---

## Problem 2
...
```

**Rules:**
- H1 (`# ...`) is the exam title once, at the top
- H2 (`## Problem N`) for every problem — GitHub auto-generates `#problem-N` as the anchor, which is what topic tables link to. Don't rename these headings.
- `*Tags:*` line is a single line, italicized, with lowercase hyphenated slugs separated by commas. `build_topic_indices.py` parses this regex: `^## Problem (\d+)\s*\n\s*\*Tags:\s*(.+?)\s*\*`
- `---` horizontal rule between problems (not after the last one)

## Tag slugs

Current topic pages and their slugs:

| Slug | File |
|---|---|
| `algebra` | [topics/algebra.md](topics/algebra.md) |
| `combinatorics` | [topics/combinatorics.md](topics/combinatorics.md) |
| `geometry` | [topics/geometry.md](topics/geometry.md) |
| `number-theory` | [topics/number-theory.md](topics/number-theory.md) |
| `probability` | [topics/probability.md](topics/probability.md) |
| `sequences-and-series` | [topics/sequences-and-series.md](topics/sequences-and-series.md) |
| `trigonometry` | [topics/trigonometry.md](topics/trigonometry.md) |

**Adding a new topic:** create `topics/<slug>.md` (copy an existing one's structure — heading, description, AUTOGEN markers), add it to [topics/README.md](topics/README.md), then use the slug in exam `*Tags:*` lines. The indexer will populate the table on next run.

## Competition directory conventions

| Competition | Directory | Filename | Problems per exam |
|---|---|---|---|
| AMC 8 | `problems/amc8/` | `<year>.md` (e.g. `2023.md`) | 25 |
| AMC 10 | `problems/amc10/` | `<year><A\|B>.md` (e.g. `2023A.md`) | 25 |
| AMC 12 | `problems/amc12/` | `<year><A\|B>.md` | 25 |
| AIME | `problems/aime/` | `<year><I\|II>.md` (e.g. `2023I.md`) | 15 |

The filename stem (`2023A`, `2023I`, etc.) is what `build_topic_indices.py` parses to extract year and variant for the table columns. Keep the pattern `<4-digit year><letter(s)>`.

## Scripts (`scripts/`)

- **`fetch_exams.py`** — scrapes AoPS wiki, writes exam .md files. Uses Python stdlib only (no deps). Rate-limited at 0.5 s per request.
- **`build_topic_indices.py`** — globs `problems/**/*.md`, extracts tags, rewrites topic tables between AUTOGEN markers.

**AoPS API endpoint used:**
```
https://artofproblemsolving.com/wiki/api.php?action=parse&page=<PAGE>&format=json&prop=wikitext&redirects=1
```

Page naming on AoPS:
- Exam index: `2023_AMC_10A_Problems`
- Per-problem: `2023_AMC_10A_Problems/Problem_1` (redirects are common for problems shared between AMC 10 and AMC 12)
- AIME: `2023_AIME_I_Problems/Problem_1`

**Markup conversions in `fetch_exams.py`:**
- `<imath>X</imath>` → `$X$`
- `<math>X</math>` → `$X$`
- `<math display="block">X</math>` → `$$X$$`
- `<cmath>X</cmath>` → `$$X$$`
- `<asy>...</asy>` → placeholder (Asymptote doesn't render in Markdown)
- `[[Image:...]]` → placeholder

## Tag heuristic caveat

`fetch_exams.py`'s `guess_tags()` is a keyword-based classifier and is **intentionally conservative** — it deliberately does NOT trigger on:

- `integer` alone (appears in nearly every AMC/AIME problem)
- `prime` alone (matches "relatively prime" in every AIME answer format)
- `square` alone (matches "perfect square", "squared", "square of")

It will still miss problems — e.g. counting problems phrased as "find the number of subsets" rather than "how many subsets". **Tags should be reviewed after fetching** and corrected by hand on the `*Tags:*` line. Then rerun `build_topic_indices.py` to refresh topic tables.

## When adding an exam from AoPS

1. `python scripts/fetch_exams.py <competition> --years <year> [--variants <letters>]`
2. Open the generated file under `problems/` and audit each problem's `*Tags:*` line
3. `python scripts/build_topic_indices.py`
4. Commit

## Things not to do

- Don't amend the AUTOGEN block by hand — your edits will be wiped on the next indexer run.
- Don't rename `## Problem N` headings (breaks topic-page links).
- Don't introduce a parallel `solutions/` tree — solutions go inline with problems.
- Don't hand-maintain topic tables — let the indexer do it.
- Don't widen the heuristic in `guess_tags()` without testing against a few existing AMC/AIME exams — the false-positive rate is what's been tuned down, not the recall.

## Environment

- Python 3.10+ (uses `|` type union syntax)
- No third-party deps — stdlib only
- Platform: Windows (paths use forward slashes in scripts for cross-platform)
