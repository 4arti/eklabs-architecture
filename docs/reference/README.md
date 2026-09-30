# Regulatory reference sources

Claude Code works from files it can read. Anything missing here, it will guess
from memory — and regulatory rules are exactly what can't be guessed. Every
rule cited in `products/ectd/profiles/` or `products/ectd/templates/` must
point at a file (via its `id` in `manifest.yaml`) in `regulatory_sources/`.

Files are filed once, by their primary axis (jurisdiction/ICH body —
matching how CTD citations are normally phrased, e.g. "ICH M4Q", "21 CFR
314"), under `regulatory_sources/`:

```
regulatory_sources/
├── global/ich/{m4,m8,q-series,s-series,e-series}/
├── global/ectd/{v3.2.2,v4.0}/
└── jurisdictions/{us,eu,canada,japan,uk,australia,india}/
    ├── structure/
    ├── module1/{v3.2.2,v4.0}/
    ├── labeling/
    ├── submission/{v3.2.2,v4.0}/
    └── guidelines/
```

Public test fixtures (EPARs, DailyMed labels, FDA 483s — anything used as
labeled eval data rather than cited guidance) live under `evals/` instead,
per spec.md §14 ("Tests live in `evals/` and run in CI"), not here.

None of the actual documents are committed to git — `manifest.yaml` lists
each one's `source_url`; `scripts/fetch_sources.py` downloads them into this
tree on demand (gitignored).

`module1/` and `submission/` split by eCTD version because the regulator
publishes genuinely separate documents per version there (e.g. FDA's Module 1
Specification v2.3 for v3.2.2 vs. its Regional Backbone Files Specification
for v4.0) — version is part of the document's identity, not just an
attribute of it. `structure/` and `labeling/` stay flat: content
requirements like 21 CFR 201.56 don't change because the backbone XML format
changed, so a version split there would sit mostly empty. This makes the
tree asymmetric within each jurisdiction on purpose — it follows the real
document boundary in each folder rather than forcing one rule everywhere.

`guidelines/` holds a region's own scientific/content guidance that ICH
hasn't harmonized — spec.md's guideline table (§7) names these per region:
FDA product-specific guidances for generics, EMA scientific guidelines,
MHLW/PMDA notifications. These aren't administrative (so they don't belong
in `module1/`/`submission/`) and aren't limited to labeling, and they
supplement rather than replace the ICH content already under `global/ich/`.
Module 1 is the only module ICH left unharmonized — Modules 2–5 (quality,
nonclinical, clinical) are covered once, globally, by the Q/S/E-series under
`global/ich/`, so a region-specific document that bears on one of them
(e.g. an FDA generics guidance touching Module 3) goes in `guidelines/` and
gets tagged `modules: [m3]` in the manifest, rather than this tree growing a
`module3/`, `module4/`, `module5/` per jurisdiction.

Every remaining folder is a true, mutually exclusive home, split on a
document's **origin** — who wrote it:

- `global/` — ICH-harmonized guidelines and the eCTD backbone specs
  themselves; not owned by any one regulator.
- `jurisdictions/{region}/` — anything a specific regulator authored,
  including that region's own validation criteria (filed under
  `submission/`) and any version-common backbone rules (filed under
  `global/ectd/{version}/`).

Product type (small molecule, biologic, biosimilar, vaccine, generic),
application type (NDA, ANDA, BLA, IND, MAA), and document type (guidance,
validation criteria, DTD, example) are **not** mutually exclusive with
origin — an FDA biosimilar-BLA validation-criteria document is
jurisdiction=us *and* product_type=biosimilar *and* application_type=bla
*and* document_type=validation_criteria all at once — so none of those are
folders. Rather than copying or symlinking the same file into every matching
combination, those axes are tagged in `regulatory_sources/manifest.yaml` on
the one physical file. Templates and profiles cite the manifest `id`, not the
raw path, so a file can move without breaking citations.

When adding a source: place the file under the right folder, add its entry to
`manifest.yaml`, and note the source URL and version date there — ICH and
agencies revise these on their own schedule (spec §7, §5), so re-check
ich.org and each agency's site before relying on a cached copy for a release.
