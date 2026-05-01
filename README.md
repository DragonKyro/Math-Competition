# Math-Competition

A compilation of problems and solutions from math competitions (AMC 8, AMC 10, AMC 12, AIME, and extendable to others), organized so you can practice by exam *or* by topic.

## Structure

```
problems/     one .md per exam — problem statements with solutions in collapsible <details>
  amc8/      2023.md, 2024.md, ...
  amc10/     2023A.md, 2023B.md, ...
  amc12/
  aime/      2023I.md, 2023II.md, ...
topics/       one .md per topic — tables linking to every problem tagged with that topic
  algebra.md
  geometry.md
  ...
templates/    blank exam template to copy when writing an exam by hand
scripts/      Python scripts that fetch exams from AoPS and regenerate topic tables
```

Each problem lives **once**, inside its exam file. Topic pages are auto-generated indexes that link into those files via heading anchors (`## Problem 15` → `#problem-15`).

## Practicing

- **By exam** — open an exam under [problems/](problems/). Solutions stay collapsed inside `<details>` blocks until you expand them.
- **By topic** — open a topic under [topics/](topics/) and click into problems one at a time. Each row tells you the source exam and any subtopics.

## Adding exams

### From the AoPS wiki (the usual path)

`scripts/fetch_exams.py` pulls exams from [artofproblemsolving.com](https://artofproblemsolving.com/) and writes them in this repo's format:

```bash
python scripts/fetch_exams.py amc10 --years 2023
python scripts/fetch_exams.py amc10 --years 2020-2024 --variants A
python scripts/fetch_exams.py aime  --years 2023
python scripts/fetch_exams.py amc8  --years 2022,2023,2024
```

Then retag based on solution text (the fetch assigns coarse broad-area tags; `retag.py` replaces them with narrow technique tags like `vietas-formulas`, `power-of-a-point`, `modular-arithmetic` by scanning solutions):

```bash
python scripts/retag.py
python scripts/build_topic_indices.py
```

See [scripts/README.md](scripts/README.md) for full flag reference and caveats (Asymptote diagrams are stripped; tagging is a keyword heuristic and should be reviewed).

### By hand

Copy [templates/exam-template.md](templates/exam-template.md) to `problems/<competition>/<year>.md` and fill it in. Each problem needs:

1. A `## Problem N` heading — this is how the heading anchor is generated
2. A `*Tags: tag1, tag2*` line — lowercase, hyphenated tag slugs (see `topics/` for the current list)
3. The problem statement
4. The solution inside a `<details><summary>Solution</summary> ... </details>` block

Then run `python scripts/build_topic_indices.py` to update the topic pages.

## Editing tags

Tags live on the `*Tags:*` line inside each problem. After editing them, rerun the indexer — the topic tables regenerate from those lines. Only content between `<!-- AUTOGEN-START -->` and `<!-- AUTOGEN-END -->` in each topic file is rewritten; the heading and description are preserved.
