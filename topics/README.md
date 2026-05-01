# Topics

Each topic page is a table of problems tagged with that topic across all competitions. Click any row to jump into the problem inside its exam file.

## Index

- [Algebra](algebra.md)
- [Geometry](geometry.md)
- [Number Theory](number-theory.md)
- [Combinatorics](combinatorics.md)
- [Probability](probability.md)
- [Trigonometry](trigonometry.md)
- [Sequences & Series](sequences-and-series.md)

## Adding a new topic

1. Create `topics/<slug>.md` following the format of the existing topic pages.
2. Add it to the index above.
3. Start using the tag in exam files under `problems/`.

## Tag conventions

- Lowercase, hyphenated (e.g. `number-theory`, not `Number Theory`).
- Pick the broadest applicable topic as the primary tag; add subtopics as extra tags on the same line (e.g. `*Tags: algebra, polynomials, Vieta's*`).
- Prefer reusing existing tags over creating new ones.
