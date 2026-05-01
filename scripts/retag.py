"""Retag every problem by scanning its solution text for specific techniques / formulas / theorems.

Narrow technique tags are detected by pattern-matching solution text (where authors explicitly
write "By Vieta's...", "Applying the law of cosines...", etc.). Problem text is also scanned
as a secondary source. When no narrow tag matches, falls back to the broad-area classifier
from fetch_exams.guess_tags (algebra, geometry, number-theory, etc.).

Usage:
  python scripts/retag.py                    # retag all exam files under problems/
  python scripts/retag.py problems/aime      # retag a subdirectory
  python scripts/retag.py --dry-run          # print tag changes without writing

After running, execute `python scripts/build_topic_indices.py` to regenerate topic tables.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys
from collections import Counter

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
PROBLEMS_DIR = REPO_ROOT / "problems"

sys.path.insert(0, str(REPO_ROOT / "scripts"))
from fetch_exams import guess_tags as broad_area_tags  # type: ignore

# Narrow-tag detection patterns. Each tag maps to a list of regexes; any match assigns the tag.
# Patterns are case-insensitive. Designed to run against solution text; false positives over
# false negatives is the preferred failure mode (user asked for a wider net).
TAG_PATTERNS: dict[str, list[str]] = {
    # --- Geometry: named theorems / formulas ---
    "pythagorean-theorem": [r"\bpythagor(?:ean|as)", r"\bPythag\b"],
    "law-of-cosines": [r"\blaw\s+of\s+cosines?\b", r"\bL[oO]C\b"],
    "law-of-sines": [r"\blaw\s+of\s+sines?\b", r"\bL[oO]S\b"],
    "power-of-a-point": [r"\bpower\s+of\s+(?:a|the)\s+point\b", r"\bPoP\b"],
    "angle-bisector-theorem": [r"\bangle\s+bisector\s+theorem\b"],
    "stewarts-theorem": [r"\bstewart['’]?s\b"],
    "ptolemys-theorem": [r"\bptolemy['’]?s?\b"],
    "cevas-theorem": [r"\bceva['’]?s\b"],
    "menelauss-theorem": [r"\bmenelaus['’]?s?\b"],
    "inscribed-angle-theorem": [r"\binscribed\s+angle(?:\s+theorem)?\b"],
    "herons-formula": [r"\bheron['’]?s\b"],
    "brahmaguptas-formula": [r"\bbrahmagupta['’]?s\b"],
    "shoelace-theorem": [r"\bshoelace\b"],
    "picks-theorem": [r"\bpick['’]?s\s+theorem\b"],

    # --- Geometry: techniques ---
    "similar-triangles": [r"\bsimilar\s+triangles?\b", r"\bAA\s+similarity\b",
                           r"\bSAS\s+similarity\b", r"\bSSS\s+similarity\b", r"\bAA\s+postulate\b"],
    "congruent-triangles": [r"\bcongruent\s+triangles?\b", r"\bSAS\s+congruence\b",
                             r"\bSSS\s+congruence\b", r"\bASA\s+congruence\b"],
    "mass-point-geometry": [r"\bmass\s+point", r"\bmass[\s-]?points?\b"],
    "coordinate-bash": [r"\bcoordinate\s+(?:bash|geometry)\b", r"\bcoord\s+bash\b"],
    "complex-bash": [r"\bcomplex\s+bash\b", r"\bcomplex\s+numbers?\s+(?:bash|approach)\b"],
    "trig-bash": [r"\btrig(?:onometric)?\s+bash\b"],
    "angle-chasing": [r"\bangle\s+chas"],
    "rotation": [r"\brotate\s+(?:the|a|triangle|figure|about)\b", r"\brotation\s+(?:by|of|about)\b"],
    "reflection": [r"\breflect\s+(?:the|over|across|about)\b", r"\breflection\s+(?:across|over|about)\b"],
    "inradius": [r"\binradius\b", r"\binscribed\s+circle\b"],
    "circumradius": [r"\bcircumradius\b", r"\bcircumscribed\s+circle\b"],
    "radical-axis": [r"\bradical\s+axis\b"],
    "spiral-similarity": [r"\bspiral\s+similarity\b"],

    # --- Algebra ---
    "vietas-formulas": [r"\bvieta['’]?s?\b"],
    "quadratic-formula": [r"\bquadratic\s+formula\b"],
    "simons-favorite-factoring": [r"\bsimon['’]?s\s+favorite\s+factoring\b", r"\bSFFT\b"],
    "am-gm-inequality": [r"\bAM[\s-]?GM\b", r"\barithmetic\s+mean[\s\S]{0,30}?geometric\s+mean\b"],
    "cauchy-schwarz-inequality": [r"\bcauchy[\s-]?schwarz\b"],
    "jensens-inequality": [r"\bjensen['’]?s\b"],
    "triangle-inequality": [r"\btriangle\s+inequality\b"],
    "binomial-theorem": [r"\bbinomial\s+theorem\b"],
    "de-moivres-theorem": [r"\bde\s+moivre", r"\bdemoivre"],
    "complex-numbers": [r"\bcomplex\s+number", r"\be\^\{i", r"\bcis\s*\("],
    "roots-of-unity": [r"\broots?\s+of\s+unity\b", r"\bnth\s+roots?\s+of\s+unity\b"],
    "polynomial-division": [r"\bpolynomial\s+(?:long\s+)?division\b", r"\bsynthetic\s+division\b"],
    "factoring": [r"\bfactoring\s+(?:the|out)", r"\bfactored\s+(?:as|into)\b",
                   r"\bdifference\s+of\s+squares\b", r"\bdifference\s+of\s+cubes\b"],
    "logarithms": [r"\blog\s+properties\b", r"\blogarithmic\s+identit",
                    r"\bchange\s+of\s+base\b", r"\blog_\w", r"\\log_"],
    "floor-function": [r"\bfloor\s+function\b", r"\\lfloor", r"\\rfloor"],
    "rational-root-theorem": [r"\brational\s+roots?\s+theorem\b"],

    # --- Number theory ---
    "modular-arithmetic": [r"\\pmod\b", r"\\equiv\b", r"\bmodular\s+arithmetic\b",
                            r"\bcongruent\s+to\s+\d+\s+mod", r"\bmod\s+\d"],
    "chinese-remainder-theorem": [r"\bchinese\s+remainder\b", r"\bCRT\b"],
    "euclidean-algorithm": [r"\beuclidean\s+algorithm\b"],
    "fermats-little-theorem": [r"\bfermat['’]?s\s+little\b", r"\bFLT\b"],
    "eulers-totient": [r"\btotient\b", r"\\phi\s*\("],
    "wilsons-theorem": [r"\bwilson['’]?s\s+theorem\b"],
    "legendres-formula": [r"\blegendre['’]?s\b"],
    "base-representations": [r"\bbase\s+(?:ten|two|three|four|five|six|seven|eight|nine|sixteen|\d+)\b",
                              r"\bbase-\d+\b", r"\bbinary\s+representation\b"],
    "diophantine-equations": [r"\bdiophantine\b", r"\bpythagorean\s+triple"],
    "parity": [r"\bparity\s+argument", r"\bparity\s+of\b"],
    "divisibility-rules": [r"\bdivisibility\s+rules?\b"],
    "prime-factorization": [r"\bprime\s+factoriz", r"\bprime\s+power\s+decomposit"],

    # --- Combinatorics ---
    "complementary-counting": [r"\bcomplementary\s+counting\b", r"\bcomplement(?:ary)?\s+count"],
    "casework": [r"\bcasework\b", r"\bcase\s+\d+[\s:.]"],
    "inclusion-exclusion": [r"\binclusion[\s-]?exclusion\b", r"\bPIE\b"],
    "stars-and-bars": [r"\bstars\s+and\s+bars\b", r"\bballs\s+(?:and|in)\s+(?:bars|urns|boxes)\b"],
    "pigeonhole-principle": [r"\bpigeonhole\b"],
    "hockey-stick-identity": [r"\bhockey[\s-]?stick\b"],
    "catalan-numbers": [r"\bcatalan\s+numbers?\b"],
    "derangements": [r"\bderangements?\b"],
    "burnsides-lemma": [r"\bburnside['’]?s\b"],
    "generating-functions": [r"\bgenerating\s+functions?\b"],
    "recursion": [r"\brecursi", r"\brecurrence\s+relation"],
    "bijection": [r"\bbijection\b", r"\bbijective\s+(?:counting|correspondence)"],
    "path-counting": [r"\bnumber\s+of\s+(?:lattice|shortest)\s+paths?\b", r"\bpath\s+counting\b",
                       r"\bgrid\s+paths?\b"],

    # --- Sequences & series ---
    "telescoping-sums": [r"\btelescop"],
    "geometric-series": [r"\bgeometric\s+(?:series|progression|sequence)\b"],
    "arithmetic-series": [r"\barithmetic\s+(?:series|progression|sequence)\b"],
    "recurrence-relations": [r"\brecurrence\s+relation"],
    "fibonacci": [r"\bfibonacci\b"],
    "induction": [r"\bby\s+induction\b", r"\bmathematical\s+induction\b",
                   r"\binductive\s+hypothesis\b"],

    # --- Probability ---
    "expected-value": [r"\bexpected\s+value\b", r"\blinearity\s+of\s+expectation\b", r"\bE\s*\["],
    "conditional-probability": [r"\bconditional\s+probability\b"],
    "geometric-probability": [r"\bgeometric\s+probability\b"],
    "complementary-probability": [r"\bcomplementary\s+probability\b"],
    "state-diagram": [r"\bstate\s+diagram\b", r"\btransition\s+matrix\b", r"\bmarkov\s+chain\b"],

    # --- Trigonometry ---
    "trig-identities": [r"\btrig(?:onometric)?\s+identit"],
    "double-angle-identities": [r"\bdouble[\s-]?angle\b"],
    "sum-to-product": [r"\bsum[\s-]to[\s-]product\b"],
    "product-to-sum": [r"\bproduct[\s-]to[\s-]sum\b"],
    "angle-addition-formulas": [r"\bangle\s+addition\b", r"\bsum\s+of\s+angles\s+formula"],
}

# Compile patterns once
COMPILED_PATTERNS: dict[str, list[re.Pattern]] = {
    tag: [re.compile(p, re.IGNORECASE) for p in patterns] for tag, patterns in TAG_PATTERNS.items()
}


def detect_narrow_tags(text: str) -> set[str]:
    """Return the set of narrow technique tags whose patterns match the given text."""
    tags: set[str] = set()
    for tag, patterns in COMPILED_PATTERNS.items():
        if any(p.search(text) for p in patterns):
            tags.add(tag)
    return tags


# --- File-level retagging ---

# Match one problem block's header + existing tags + body, stopping at the next header or EOF.
PROBLEM_BLOCK_RE = re.compile(
    r"(## Problem \d+\s*\n\s*\*Tags:\s*)([^\*\n]+?)(\s*\*\s*\n)(.*?)(?=(?:\n## Problem \d+|\Z))",
    re.MULTILINE | re.DOTALL,
)

# Match the solution <details> block inside a problem body.
SOLUTION_RE = re.compile(r"<details><summary>Solution</summary>(.+?)</details>", re.DOTALL)


def retag_problem_block(problem_body: str, problem_text_hint: str) -> list[str]:
    """Given a problem's body (problem text + solution block) and a problem-text hint,
    return the list of tags to assign.
    """
    solution_match = SOLUTION_RE.search(problem_body)
    solution_text = solution_match.group(1) if solution_match else ""
    problem_text = problem_body[: solution_match.start()] if solution_match else problem_body

    # Scan both problem statement and solutions for narrow-tag mentions
    narrow = detect_narrow_tags(solution_text + "\n" + problem_text)

    if narrow:
        return sorted(narrow)

    # Fallback: broad-area classifier (on problem text only, like fetch_exams)
    return broad_area_tags(problem_text_hint or problem_text)


def retag_file(path: pathlib.Path, dry_run: bool = False) -> tuple[int, int, Counter]:
    """Retag every problem. Returns (problems_seen, problems_changed, new-tag-frequency)."""
    text = path.read_text(encoding="utf-8")
    changed = 0
    seen = 0
    tag_counts: Counter[str] = Counter()

    def replace(match: re.Match) -> str:
        nonlocal changed, seen
        seen += 1
        header_prefix = match.group(1)
        old_tags = match.group(2).strip()
        tags_suffix = match.group(3)
        body = match.group(4)

        new_tags = retag_problem_block(body, body)
        new_tags_str = ", ".join(new_tags)
        if new_tags_str != old_tags:
            changed += 1
        for t in new_tags:
            tag_counts[t] += 1
        return f"{header_prefix}{new_tags_str}{tags_suffix}{body}"

    new_text = PROBLEM_BLOCK_RE.sub(replace, text)
    if new_text != text and not dry_run:
        path.write_text(new_text, encoding="utf-8")
    return seen, changed, tag_counts


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("paths", nargs="*", help="optional exam files or directories to retag (default: all of problems/)")
    parser.add_argument("--dry-run", action="store_true", help="do not write files; print summary only")
    args = parser.parse_args(argv)

    roots = [pathlib.Path(p) for p in args.paths] if args.paths else [PROBLEMS_DIR]

    files: list[pathlib.Path] = []
    for root in roots:
        if root.is_file():
            files.append(root)
        else:
            files.extend(sorted(p for p in root.rglob("*.md") if p.name != "README.md"))

    tag_counter: Counter[str] = Counter()
    total_seen = 0
    total_changed = 0
    for f in files:
        seen, changed, counts = retag_file(f, dry_run=args.dry_run)
        total_seen += seen
        total_changed += changed
        tag_counter.update(counts)

    print(f"processed {len(files)} files, {total_seen} problems, {total_changed} retagged"
          + (" (dry run)" if args.dry_run else ""))
    print(f"unique tags applied: {len(tag_counter)}")
    print()
    print("tag frequency (all tags, descending):")
    for tag, n in tag_counter.most_common():
        print(f"  {n:5d}  {tag}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
