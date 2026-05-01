"""Discover, download, and scaffold round-based contests (PUMaC, CMIMC).

PUMaC source: https://jason-shi-f9dm.squarespace.com/archives
CMIMC source: https://cmimc.math.cmu.edu/math/past-problems/<year>

This script does three things:

  1. `--discover` — scrape the archive pages to build `.scratch/<comp>_inventory.json`:
     a list of {year, round_name, round_slug, kind (problems|solutions), url, filename}.
  2. `--download` — fetch every PDF in the inventory into `.scratch/<comp>/<filename>`,
     rate-limited and idempotent (skips already-downloaded files by size).
  3. `--skeletons` — for every (year, round) in the inventory, create a stub
     `problems/<comp>/<round_slug>/<year>.md` if missing, containing only the
     competition header and links to the source PDFs. Existing files are never
     overwritten — hand-transcribed problems are preserved.

Usage:
  python scripts/fetch_round_contests.py --comp pumac --discover --download --skeletons
  python scripts/fetch_round_contests.py --comp cmimc --all

The --all flag is equivalent to --discover --download --skeletons. Discovery is
cached in `.scratch/<comp>_inventory.json`; rerun with --discover to refresh.

Rate limit: 0.5 s per HTTP request (archive pages and PDF downloads). No
third-party deps.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, asdict

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRATCH = REPO_ROOT / ".scratch"
PROBLEMS_DIR = REPO_ROOT / "problems"
USER_AGENT = "Mozilla/5.0 (Math-Competition repo scraper)"
SLEEP_SECONDS = 0.5

PUMAC_ARCHIVE = "https://jason-shi-f9dm.squarespace.com/archives"
PUMAC_HOST = "https://jason-shi-f9dm.squarespace.com"
CMIMC_YEAR_PAGE = "https://cmimc.math.cmu.edu/math/past-problems/{year}"
CMIMC_YEARS = list(range(2016, 2026))  # 2016..2025


@dataclass
class Entry:
    year: int
    round_name: str           # human label, e.g. "Algebra A"
    round_slug: str           # directory slug, e.g. "algebra-a"
    kind: str                 # "problems" or "solutions"
    url: str                  # absolute URL
    filename: str             # .scratch/<comp>/<filename>


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def slugify(name: str) -> str:
    s = name.strip().lower()
    s = s.replace("&", " and ")
    s = re.sub(r"['`]", "", s)
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def http_get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    time.sleep(SLEEP_SECONDS)
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def http_get_text(url: str) -> str:
    return http_get(url).decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# PUMaC discovery
# ---------------------------------------------------------------------------

# Canonical PUMaC round names. Division A/B are suffixes applied in parsing.
PUMAC_BASE_ROUNDS = {
    # <strong> label (uppercase-normalized) -> canonical name
    "ALGEBRA": "Algebra",
    "COMBINATORICS": "Combinatorics",
    "GEOMETRY": "Geometry",
    "NUMBER THEORY": "Number Theory",
    "INDIVIDUAL FINALS": "Individual Finals",
    "INDIV. FINALS": "Individual Finals",
    "INDIV FINALS": "Individual Finals",
    "FINALS": "Individual Finals",
}


def _pumac_year_spans(html: str) -> list[tuple[int, int, int]]:
    """Return list of (year, start_idx, end_idx) for each year's content span.

    The archive page has three decorative `<h1>YEAR</h1>` tags per year; we take
    the first occurrence in the main content flow (after the TOC) as the start,
    and the next year's first h1 (or end-of-document) as the end.
    """
    # Locate TOC end: skip the initial table of year links.
    toc_end = html.find("parallax-images")
    search_start = toc_end if toc_end > 0 else 0

    pattern = re.compile(r'<h1[^>]*>\s*(\d{4})\*?\s*</h1>', re.IGNORECASE)
    firsts: dict[int, int] = {}
    for m in pattern.finditer(html, search_start):
        year = int(m.group(1))
        if year not in firsts:
            firsts[year] = m.start()
    years_sorted = sorted(firsts.items(), key=lambda x: x[1])
    spans: list[tuple[int, int, int]] = []
    for i, (year, start) in enumerate(years_sorted):
        end = years_sorted[i + 1][1] if i + 1 < len(years_sorted) else len(html)
        spans.append((year, start, end))
    return spans


def _pumac_parse_year(html: str, year: int) -> list[Entry]:
    """Parse a single year's HTML block into Entry rows."""
    entries: list[Entry] = []

    # Identify division/section subheaders within this year.
    # <h2>Division A</h2>, <h2>Division B</h2>, <h2>Team Round</h2>, etc.
    section_pat = re.compile(r'<h2[^>]*>\s*([^<]+?)\s*</h2>', re.IGNORECASE)
    section_markers = [(m.start(), m.group(1).strip()) for m in section_pat.finditer(html)]

    def section_for(pos: int) -> str:
        current = ""
        for spos, label in section_markers:
            if spos <= pos:
                current = label
            else:
                break
        return current

    # Walk every <a href="/s/*.pdf">TEXT</a>. Link text may wrap inner tags
    # like <strong>problems</strong>, so we use a non-greedy match and strip HTML.
    link_pat = re.compile(
        r'<a\s+[^>]*href="(/s/[^"]+\.pdf)"[^>]*>(.*?)</a>',
        re.IGNORECASE | re.DOTALL,
    )

    # Cache <strong>LABEL</strong> positions for round lookup.
    strong_pat = re.compile(r'<strong[^>]*>\s*([^<]+?)\s*</strong>', re.IGNORECASE)
    strong_markers = [(m.start(), m.group(1).strip()) for m in strong_pat.finditer(html)]

    def nearest_round_before(pos: int) -> str | None:
        """Find the most recent <strong>...</strong> whose label maps to a round."""
        for spos, label in reversed([(p, l) for p, l in strong_markers if p < pos]):
            up = re.sub(r"\s+", " ", label.upper()).strip(". ")
            if up in PUMAC_BASE_ROUNDS:
                return PUMAC_BASE_ROUNDS[up]
            # Some years use "ALGEBRA A" / "INDIVIDUAL FINALS A" directly in the strong tag.
            for key, canon in PUMAC_BASE_ROUNDS.items():
                if up.startswith(key):
                    return canon
        return None

    # Also some older years omit <strong> wrappers and put the round name as plain h3/h2 text.
    # We fall back to searching the nearest text header before the link.
    h_pat = re.compile(r'<h[1-4][^>]*>\s*([^<][^<]*?)\s*</h[1-4]>', re.IGNORECASE)
    h_markers = [(m.start(), m.group(1).strip()) for m in h_pat.finditer(html)]

    def nearest_round_from_headers(pos: int) -> str | None:
        for spos, label in reversed([(p, l) for p, l in h_markers if p < pos]):
            up = re.sub(r"\s+", " ", label.upper()).strip(". ")
            for key, canon in PUMAC_BASE_ROUNDS.items():
                if key in up:
                    return canon
        return None

    for m in link_pat.finditer(html):
        url_path = m.group(1)
        raw = m.group(2)
        # Strip any inner HTML tags (e.g. <strong>) from the link text.
        link_text = re.sub(r"<[^>]+>", " ", raw)
        link_text = re.sub(r"\s+", " ", link_text).strip()
        lt_low = link_text.lower()
        if not (("problem" in lt_low) or ("solution" in lt_low) or ("test" in lt_low) or ("answer" in lt_low)):
            # Some archive rows list an orphan link without problems/solutions text; skip.
            continue

        section = section_for(m.start())
        sec_up = section.upper()

        # Determine round base and whether this section has an A/B suffix.
        round_base: str | None = None
        suffix = ""
        if "DIVISION A" in sec_up:
            suffix = "A"
            round_base = nearest_round_before(m.start()) or nearest_round_from_headers(m.start())
        elif "DIVISION B" in sec_up:
            suffix = "B"
            round_base = nearest_round_before(m.start()) or nearest_round_from_headers(m.start())
        elif "TEAM" in sec_up:
            round_base = "Team"
        elif "POWER" in sec_up:
            round_base = "Power"
        elif "LIVE" in sec_up:
            round_base = "Live"
        else:
            # Outside any recognized section; try to infer from strong label.
            round_base = nearest_round_before(m.start())

        if not round_base:
            continue

        round_name = f"{round_base} {suffix}".strip() if suffix else round_base
        round_slug = slugify(round_name)

        kind = "solutions" if "solution" in lt_low else "problems"

        # Normalize Squarespace "/s/..." -> absolute URL.
        abs_url = PUMAC_HOST + url_path
        filename = url_path.rsplit("/", 1)[-1]

        entries.append(Entry(
            year=year,
            round_name=round_name,
            round_slug=round_slug,
            kind=kind,
            url=abs_url,
            filename=filename,
        ))

    return entries


def discover_pumac() -> list[Entry]:
    html = http_get_text(PUMAC_ARCHIVE)
    entries: list[Entry] = []
    for year, start, end in _pumac_year_spans(html):
        entries.extend(_pumac_parse_year(html[start:end], year))
    # De-dupe (filename + year + round + kind) — Squarespace sometimes duplicates rows.
    seen = set()
    uniq: list[Entry] = []
    for e in entries:
        key = (e.year, e.round_slug, e.kind, e.filename)
        if key in seen:
            continue
        seen.add(key)
        uniq.append(e)
    return uniq


# ---------------------------------------------------------------------------
# CMIMC discovery
# ---------------------------------------------------------------------------

# CMIMC aria-labels alternate "<Round Name>" and "Solutions" per year page.

def _cmimc_rename(year: int, round_name: str) -> str:
    # CMIMC combined its Algebra and Number Theory rounds starting in 2019.
    # The website aria-labels it "Algebra" but the PDFs are titled
    # "Algebra and Number Theory" — match the latter so topic indexing stays
    # consistent with the existing 2023 hand-transcribed file.
    if round_name == "Algebra" and year >= 2019:
        return "Algebra and Number Theory"
    return round_name


def _cmimc_parse_year(html: str, year: int) -> list[Entry]:
    entries: list[Entry] = []
    # Extract ordered (drive_id, aria_label, position) triples — the page lists
    # them in the order "Round, Solutions, Round, Solutions, ...".
    pat = re.compile(
        r'<a\s+[^>]*href="https://drive\.google\.com/file/d/([A-Za-z0-9_-]+)[^"]*"[^>]*aria-label="([^"]+)"',
        re.IGNORECASE | re.DOTALL,
    )
    items = [(m.group(1), m.group(2).strip(), m.start()) for m in pat.finditer(html)]
    if not items:
        return []

    # 2021 and 2022 (so far) split the individual rounds across
    # "Division 1 Individual" / "Division 2 Individual" sections. When present,
    # we suffix the round name with the division number so slug collisions like
    # "algebra-and-number-theory" don't conflate two different exams.
    div_pat = re.compile(r'Division\s*(\d)\s*Individual', re.IGNORECASE)
    div_markers = [(m.start(), m.group(1)) for m in div_pat.finditer(html)]
    # Rounds that appear only in divisional sections get a suffix; rounds that
    # typically appear outside divisions (Computer Science, Team, Integration
    # Bee, MathDash, Power, Finals) don't, even if their HTML position falls
    # after a Division header.
    DIVISIONAL_ROUNDS = {"Algebra", "Algebra and Number Theory", "Combinatorics", "Geometry", "Number Theory"}

    def division_for(pos: int) -> str | None:
        current = None
        for dpos, dnum in div_markers:
            if dpos <= pos:
                current = dnum
            else:
                break
        return current

    current_round: str | None = None
    for drive_id, label, pos in items:
        lab_low = label.lower()
        if lab_low == "solutions":
            kind = "solutions"
            round_name = current_round
        else:
            kind = "problems"
            base = _cmimc_rename(year, label)
            div = division_for(pos)
            if div and base in DIVISIONAL_ROUNDS:
                round_name = f"{base} Division {div}"
            else:
                round_name = base
            current_round = round_name
        if not round_name:
            continue
        round_slug = slugify(round_name)
        filename = f"CMIMC_{year}_{round_name.replace(' ', '_')}_{kind.capitalize()}.pdf"
        url = f"https://drive.google.com/uc?id={drive_id}&export=download"
        entries.append(Entry(
            year=year,
            round_name=round_name,
            round_slug=round_slug,
            kind=kind,
            url=url,
            filename=filename,
        ))
    # Dedup by (year, round_slug, kind, drive_id-in-url) — an abundance of
    # caution in case a page mirrors a link twice.
    seen = set()
    uniq = []
    for e in entries:
        key = (e.year, e.round_slug, e.kind, e.url)
        if key in seen:
            continue
        seen.add(key)
        uniq.append(e)
    return uniq


def discover_cmimc() -> list[Entry]:
    entries: list[Entry] = []
    for year in CMIMC_YEARS:
        url = CMIMC_YEAR_PAGE.format(year=year)
        try:
            html = http_get_text(url)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                continue
            raise
        entries.extend(_cmimc_parse_year(html, year))
    return entries


# ---------------------------------------------------------------------------
# Download & skeleton generation
# ---------------------------------------------------------------------------


def download_all(comp: str, entries: list[Entry]) -> None:
    out_dir = SCRATCH / comp
    out_dir.mkdir(parents=True, exist_ok=True)
    total = len(entries)
    for i, e in enumerate(entries, 1):
        path = out_dir / e.filename
        if path.exists() and path.stat().st_size > 1024:
            continue
        try:
            data = http_get(e.url)
        except Exception as err:
            print(f"  [{i}/{total}] FAIL {e.filename}: {err}")
            continue
        # Heuristic: Google Drive sometimes returns HTML (virus-scan page) for larger files.
        if data[:4] == b"%PDF":
            path.write_bytes(data)
            print(f"  [{i}/{total}] OK   {e.filename} ({len(data):,} bytes)")
        elif len(data) < 100_000 and b"<html" in data[:1000].lower():
            print(f"  [{i}/{total}] SKIP {e.filename}: got HTML (Drive virus scan?)")
        else:
            # Non-PDF but non-HTML; write anyway and warn.
            path.write_bytes(data)
            print(f"  [{i}/{total}] WARN {e.filename}: not %PDF magic; wrote {len(data):,} bytes")


def skeleton_path(comp: str, entry: Entry) -> pathlib.Path:
    return PROBLEMS_DIR / comp / entry.round_slug / f"{entry.year}.md"


COMP_DISPLAY = {"pumac": "PUMaC", "cmimc": "CMIMC"}


def build_skeleton(comp: str, year: int, round_name: str, sources: list[Entry]) -> str:
    display = COMP_DISPLAY[comp]
    lines = [
        f"# {year} {display} {round_name}",
        "",
        "_Problems and solutions not yet transcribed._",
        "",
        "**Sources:**",
    ]
    for e in sorted(sources, key=lambda x: x.kind):
        lines.append(f"- [{e.kind.capitalize()} PDF]({e.url}) — local: `.scratch/{comp}/{e.filename}`")
    lines.append("")
    lines.append(
        "<!-- Transcribe problems below following CLAUDE.md conventions. "
        "Use `## Problem N` headings, `*Tags: ...*` lines, and solutions inside "
        "`<details><summary>Solution</summary> ... </details>`. Remove this comment "
        "and the placeholder above when done. -->"
    )
    lines.append("")
    return "\n".join(lines)


def generate_skeletons(comp: str, entries: list[Entry]) -> None:
    # Group by (year, round_slug) and collect sources.
    groups: dict[tuple[int, str], list[Entry]] = {}
    for e in entries:
        groups.setdefault((e.year, e.round_slug), []).append(e)

    made = 0
    skipped = 0
    for (year, slug), items in sorted(groups.items()):
        round_name = items[0].round_name
        path = PROBLEMS_DIR / comp / slug / f"{year}.md"
        if path.exists():
            skipped += 1
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(build_skeleton(comp, year, round_name, items), encoding="utf-8")
        made += 1
    print(f"skeletons: {made} created, {skipped} already present")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def inventory_path(comp: str) -> pathlib.Path:
    return SCRATCH / f"{comp}_inventory.json"


def load_inventory(comp: str) -> list[Entry]:
    path = inventory_path(comp)
    if not path.exists():
        raise SystemExit(
            f"no inventory at {path}. rerun with --discover to fetch it."
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    return [Entry(**row) for row in data]


def save_inventory(comp: str, entries: list[Entry]) -> None:
    SCRATCH.mkdir(parents=True, exist_ok=True)
    path = inventory_path(comp)
    path.write_text(
        json.dumps([asdict(e) for e in entries], indent=2),
        encoding="utf-8",
    )
    print(f"wrote {len(entries)} entries to {path}")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--comp", choices=["pumac", "cmimc", "all"], default="all")
    p.add_argument("--discover", action="store_true", help="Re-scrape archive pages.")
    p.add_argument("--download", action="store_true", help="Fetch PDFs into .scratch/<comp>/.")
    p.add_argument("--skeletons", action="store_true", help="Create missing skeleton .md files.")
    p.add_argument("--all", action="store_true", help="Short for --discover --download --skeletons.")
    args = p.parse_args()

    if args.all:
        args.discover = args.download = args.skeletons = True
    if not (args.discover or args.download or args.skeletons):
        p.error("pick at least one of --discover / --download / --skeletons / --all")

    comps = ["pumac", "cmimc"] if args.comp == "all" else [args.comp]

    for comp in comps:
        print(f"=== {comp.upper()} ===")
        if args.discover:
            print("discovering...")
            entries = discover_pumac() if comp == "pumac" else discover_cmimc()
            save_inventory(comp, entries)
        else:
            entries = load_inventory(comp)
            print(f"loaded {len(entries)} entries from cache")

        if args.download:
            print(f"downloading {len(entries)} PDFs...")
            download_all(comp, entries)

        if args.skeletons:
            generate_skeletons(comp, entries)

    return 0


if __name__ == "__main__":
    sys.exit(main())
