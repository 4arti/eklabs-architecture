---
paths:
  - "products/ectd/**"
---

# products/ectd/

Templates and profiles are data, not judgment calls — every section requirement,
Module 1 rule, and format date must cite the ICH/FDA source file it comes from
(in `docs/reference/`). If you can't find the source, say so and stop instead
of guessing.

- Profiles (`products/ectd/profiles/`): one YAML per authority. See spec §5.
- Templates (`products/ectd/templates/`): one YAML per section/region variant,
  structured per ICH M4 (M4Q/M4S/M4E). Each slot cites its guideline and version
  (spec §7).
- `publishers/` and `validation/` are plain code — no AI, per the hard rule in
  `CLAUDE.md`.
