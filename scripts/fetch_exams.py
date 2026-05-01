"""Fetch AoPS wiki exam pages and write Markdown files in this repo's format.

Usage:
  python scripts/fetch_exams.py amc10 --years 2023
  python scripts/fetch_exams.py amc10 --years 2022,2023,2024 --variants A,B
  python scripts/fetch_exams.py amc10 --years 2020-2024
  python scripts/fetch_exams.py aime  --years 2023
  python scripts/fetch_exams.py amc8  --years 2023

Defaults to fetching both variants (A/B for AMC 10/12, I/II for AIME) when --variants is omitted.
AMC 8 has no variants.

After fetching, run `python scripts/build_topic_indices.py` to regenerate topics/*.md tables.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

AOPS_API = "https://artofproblemsolving.com/wiki/api.php"
USER_AGENT = "math-competition-repo-scraper/1.0 (personal use; educational)"
REQUEST_INTERVAL_SEC = 0.5

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
PROBLEMS_DIR = REPO_ROOT / "problems"

COMPETITIONS = {
    "amc8":  {"problems": 25, "default_variants": [""],            "display": "AMC 8"},
    "amc10": {"problems": 25, "default_variants": ["", "A", "B"],  "display": "AMC 10"},
    "amc12": {"problems": 25, "default_variants": ["", "A", "B"],  "display": "AMC 12"},
    "aime":  {"problems": 15, "default_variants": ["", "I", "II"], "display": "AIME"},
}


def page_base(competition: str, year: int, variant: str) -> str:
    """Build the AoPS wiki page name root (before `_Problems/Problem_N`)."""
    if competition == "amc8":
        return f"{year}_AMC_8"
    if competition == "amc10":
        return f"{year}_AMC_10{variant}"
    if competition == "amc12":
        return f"{year}_AMC_12{variant}"
    if competition == "aime":
        return f"{year}_AIME_{variant}" if variant else f"{year}_AIME"
    raise ValueError(competition)

KNOWN_TOPIC_SLUGS = {
    "algebra",
    "geometry",
    "number-theory",
    "combinatorics",
    "probability",
    "trigonometry",
    "sequences-and-series",
}


def fetch_wikitext(page: str) -> str:
    params = urllib.parse.urlencode(
        {"action": "parse", "page": page, "format": "json", "prop": "wikitext", "redirects": "1"}
    )
    url = f"{AOPS_API}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return ""
        raise
    return data.get("parse", {}).get("wikitext", {}).get("*", "")


def aops_math_to_latex(text: str) -> str:
    text = re.sub(r"<cmath>(.+?)</cmath>", r"$$\1$$", text, flags=re.DOTALL)
    text = re.sub(r"<imath>(.+?)</imath>", r"$\1$", text, flags=re.DOTALL)
    text = re.sub(r"<math\s+display=['\"]?block['\"]?>(.+?)</math>", r"$$\1$$", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<math>(.+?)</math>", r"$\1$", text, flags=re.DOTALL)
    return text


def strip_asymptote(text: str) -> str:
    return re.sub(r"<asy>.*?</asy>", "_(Asymptote diagram omitted — see AoPS for image)_", text, flags=re.DOTALL)


def strip_images(text: str) -> str:
    return re.sub(r"\[\[Image:[^\]]*\]\]", "_(image omitted — see AoPS)_", text)


def split_sections(wt: str) -> list[tuple[str, str]]:
    parts = re.split(r"^==\s*([^=]+?)\s*==\s*$", wt, flags=re.MULTILINE)
    sections = []
    for i in range(1, len(parts), 2):
        heading = parts[i].strip()
        body = parts[i + 1] if i + 1 < len(parts) else ""
        sections.append((heading, body.strip()))
    return sections


def parse_problem_page(wt: str) -> tuple[str, list[tuple[str, str]]]:
    problem_text = ""
    solutions: list[tuple[str, str]] = []
    for heading, body in split_sections(wt):
        low = heading.lower()
        if low == "problem":
            problem_text = body
        elif low.startswith("solution"):
            solutions.append((heading, body))
    return problem_text, solutions


def guess_tags(problem_text: str) -> list[str]:
    """Keyword-based topic classifier. Intentionally conservative to avoid false positives
    from AMC/AIME boilerplate ("relatively prime positive integers", "perfect square", etc.).
    """
    raw = problem_text.lower()
    # Neutralize common stock phrases that trigger false positives
    t = raw
    for phrase in ("relatively prime", "perfect square", "perfect cube", "square of", "squared"):
        t = t.replace(phrase, " ")

    tags: set[str] = set()

    # Probability
    if any(k in raw for k in ["probability", "at random", "chance that ", "expected value", "expected number"]):
        tags.add("probability")

    # Combinatorics
    if any(k in raw for k in ["how many ways", "how many arrangements", "how many subsets", "how many orderings",
                              "how many ordered", "how many distinct", "how many permutations",
                              "distinguishable", "indistinguishable"]):
        tags.add("combinatorics")

    # Number theory — require strong NT signals, not just "integer" / "digit" / "prime" alone
    nt_keywords = ["divisible by", "divisor", "prime number", "prime factor", "primes less", "is prime",
                   "factorization", "remainder when", "modulo", " mod ", "modular arithmetic",
                   "base-", "base ten", "base-two", "gcd", "greatest common divisor",
                   "lcm", "least common multiple", "consecutive integer"]
    if any(k in raw for k in nt_keywords):
        tags.add("number-theory")
    # "perfect square" / "perfect cube" are number-theoretic (check in raw, not neutralized t)
    if "perfect square" in raw or "perfect cube" in raw:
        tags.add("number-theory")

    # Trigonometry
    if any(k in raw for k in ["\\sin", "\\cos", "\\tan", "law of sines", "law of cosines", "trigonometric"]):
        tags.add("trigonometry")

    # Sequences & series
    if any(k in raw for k in ["sequence", "arithmetic progression", "geometric progression",
                              "recurrence", "recursive", "fibonacci", "telescoping",
                              "sum of the first", "partial sum", "a_{n+1}", "a_n ="]):
        tags.add("sequences-and-series")

    # Geometry — use neutralized text so "perfect square" / "squared" don't trigger
    geom_shape = ["triangle", "circle", "polygon", "pentagon", "hexagon", "octagon",
                  "parallelogram", "trapezoid", "rhombus", "rectangle", "quadrilateral",
                  " cube", "sphere", "cone", "cylinder", "prism", "tetrahedron"]
    geom_spatial = ["inscribed", "circumscribed", "perimeter", "area of", "volume of",
                    "perpendicular", "tangent to", "tangent line", "diameter",
                    "midpoint", "altitude", "angle bisector", "vertices of the",
                    "centroid", "incircle", "circumcircle", "convex"]
    if any(k in t for k in geom_shape) or any(k in t for k in geom_spatial):
        tags.add("geometry")
    # Plain "square" only counts as geometry if accompanied by a spatial term
    if " square" in t and any(k in t for k in ["inscribed", "side", "area", "vertex", "vertices", "diagonal"]):
        tags.add("geometry")

    # Algebra
    if any(k in raw for k in ["polynomial", "inequality", "function $f(", "roots of", "vieta",
                              "quadratic", "logarith", "\\log", "exponential function",
                              "system of equations", "coefficient"]):
        tags.add("algebra")

    if not tags:
        tags.add("algebra")
    return sorted(tags)


def render_problem(n: int, problem_text: str, solutions: list[tuple[str, str]], tags: list[str]) -> str:
    problem_md = aops_math_to_latex(strip_images(strip_asymptote(problem_text))).strip()

    lines = [f"## Problem {n}", f"*Tags: {', '.join(tags)}*", "", problem_md, "", "<details><summary>Solution</summary>", ""]
    for i, (heading, body) in enumerate(solutions, 1):
        body_md = aops_math_to_latex(strip_images(strip_asymptote(body))).strip()
        label = heading if heading.lower() != "solution" else f"Solution {i}"
        lines.append(f"**{label}.**")
        lines.append("")
        lines.append(body_md)
        lines.append("")
    lines.append("</details>")
    return "\n".join(lines)


def build_exam_md(title: str, problems: list[tuple[int, str, list[tuple[str, str]], list[str]]]) -> str:
    parts = [f"# {title}", ""]
    for idx, (n, prob, sols, tags) in enumerate(problems):
        parts.append(render_problem(n, prob, sols, tags))
        if idx < len(problems) - 1:
            parts.append("")
            parts.append("---")
            parts.append("")
    parts.append("")
    return "\n".join(parts)


def fetch_exam(competition: str, year: int, variant: str):
    """Fetch all problems for one exam. Returns (title, problems) or None if the exam is not on AoPS."""
    cfg = COMPETITIONS[competition]
    base = page_base(competition, year, variant)

    # Probe Problem 1 before committing to a full fetch
    probe_wt = fetch_wikitext(f"{base}_Problems/Problem_1")
    time.sleep(REQUEST_INTERVAL_SEC)
    if not probe_wt:
        return None

    problems: list[tuple[int, str, list[tuple[str, str]], list[str]]] = []

    probe_problem, probe_solutions = parse_problem_page(probe_wt)
    if probe_problem:
        problems.append((1, probe_problem, probe_solutions, guess_tags(probe_problem)))
    else:
        problems.append((1, "_(could not parse)_", [], ["algebra"]))

    for n in range(2, cfg["problems"] + 1):
        wt = fetch_wikitext(f"{base}_Problems/Problem_{n}")
        if not wt:
            problems.append((n, "_(not available on AoPS)_", [], ["algebra"]))
        else:
            problem_text, solutions = parse_problem_page(wt)
            if not problem_text:
                problems.append((n, "_(could not parse)_", [], ["algebra"]))
            else:
                problems.append((n, problem_text, solutions, guess_tags(problem_text)))
        time.sleep(REQUEST_INTERVAL_SEC)

    title = f"{year} {cfg['display']}"
    if variant:
        title = f"{title} {variant}"
    return title, problems


def write_exam(competition: str, year: int, variant: str, overwrite: bool) -> str:
    """Returns one of: 'written', 'existed', 'missing'."""
    filename = f"{year}{variant}.md"
    dest = PROBLEMS_DIR / competition / filename
    if dest.exists() and not overwrite:
        print(f"[skip]    {dest.relative_to(REPO_ROOT)} already exists — pass --overwrite to replace")
        return "existed"

    result = fetch_exam(competition, year, variant)
    if result is None:
        print(f"[missing] {competition} {year}{variant} — not found on AoPS, skipping")
        return "missing"

    title, problems = result
    md = build_exam_md(title, problems)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(md, encoding="utf-8")
    print(f"[write]   {dest.relative_to(REPO_ROOT)}")
    return "written"


def parse_years(spec: str) -> list[int]:
    years: set[int] = set()
    for token in spec.split(","):
        token = token.strip()
        if not token:
            continue
        if "-" in token:
            start, end = token.split("-", 1)
            years.update(range(int(start), int(end) + 1))
        else:
            years.add(int(token))
    return sorted(years)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("competition", choices=sorted(COMPETITIONS.keys()))
    parser.add_argument("--years", required=True, help="comma-separated years or ranges, e.g. '2023' or '2020-2024,2022'")
    parser.add_argument("--variants", help="comma-separated variants (A,B or I,II). Defaults to all variants for this competition.")
    parser.add_argument("--overwrite", action="store_true", help="replace existing .md files")
    args = parser.parse_args(argv)

    cfg = COMPETITIONS[args.competition]
    variants = [v.strip() for v in args.variants.split(",")] if args.variants else cfg["default_variants"]

    years = parse_years(args.years)
    counts = {"written": 0, "existed": 0, "missing": 0}
    for year in years:
        for variant in variants:
            status = write_exam(args.competition, year, variant, args.overwrite)
            counts[status] += 1
    print(f"done. written={counts['written']} already-existed={counts['existed']} not-on-aops={counts['missing']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
