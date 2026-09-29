# Technical Build Spec

How to build the plan on the main tab: one Python backend, one Postgres database, one Next.js app, with the CTD/eCTD platform built first.

## 1. Stack

| Part            | Choice                                                                                                                                                                           | Why                                                                                               |
| --------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| Backend         | Python 3.12, FastAPI, Pydantic, SQLAlchemy + Alembic                                                                                                                             | AI, PDF, XML and Word tooling all live in Python                                                  |
| Database        | Postgres 16 + pgvector                                                                                                                                                           | One store for data, search vectors and agent checkpoints; row-level security separates clients    |
| Knowledge graph | Neo4j                                                                                                                                                                            | Regulatory rules and required sections are a graph (needed from Phase 3; gap analysis extends it) |
| Files           | S3 (supabase)                                                                                                                                                                    | Uploaded sources, rendered PDFs, exported packages                                                |
| Background jobs | Redis + Arq                                                                                                                                                                      | Parsing, drafting and publishing run off the request path                                         |
| Agents          | LangGraph + Postgres checkpoints                                                                                                                                                 | Fixed step workflows that can pause for a human and resume                                        |
| LLMs            | Claude via the Anthropic API: Haiku 4.5 (classify), Sonnet 5 (extract, draft), Opus 5.5 (independent checker on high-stakes text)                                                | Tool calling and structured output; zero-data-retention terms for client data                     |
| Embeddings      | Voyage AI                                                                                                                                                                        | Retrieval quality on technical text                                                               |
| Parsing         | PyMuPDF, Azure Document Intelligence (scans and tables), Docling (Word, open-source fallback), pandas (Excel), LibreOffice headless (RTF, DOCX→PDF), pikepdf (bookmarks, links) | Covers every source format and the PDF output rules                                               |
| XML             | lxml                                                                                                                                                                             | eCTD 3.2.2 and 4.0 backbones, SPL, schema validation                                              |
| Frontend        | Next.js + TypeScript + shadcn/ui, TipTap editor, react-pdf viewer                                                                                                                | Editor with locked facts and citations; side-by-side source view                                  |
| Auth            | Clerk (MFA, organisations)                                                                                                                                                       | Not worth building                                                                                |
| Ops             | Docker Compose on one VM, Sentry, Langfuse (AI traces), GitHub Actions                                                                                                           | One box until a client needs more                                                                 |

## 2. System architecture

The browser talks only to the API. Anything slow — parsing, drafting, publishing — becomes a background job, and the browser watches its progress live.

&#91;embedded content: system architecture · web, API, workers, three stores, external APIs\]

## 3. Repo layout

One repository. `platform/` is shared and never imports from `products/`; a CI check enforces this, which is what keeps it a platform.

```
eklabs/
├── apps/web                 Next.js app
├── apps/api                 FastAPI app + background worker
├── platform/
│   ├── core/                auth, tenants, database, audit log
│   ├── ingestion/           parse every file type into pages, tables, chunks
│   ├── knowledge/           search, knowledge graph
│   ├── templates/           template engine, fact store
│   ├── llm/                 the only code that calls Claude; prompt versions
│   ├── evidence/            citation and number checks
│   ├── agents/              LangGraph runtime, shared tools
│   └── review/              approvals, e-signatures
├── products/
│   ├── ectd/
│   │   ├── profiles/        one file per authority (formats, rules, dates)
│   │   ├── templates/       section templates, M1–M5
│   │   ├── agents/          planner, drafter, cross-validator
│   │   ├── publishers/      ctd_pdf, ectd_v3, ectd_v4
│   │   └── validation/      technical checks per format
│   └── gap/                 built in Phase 6
└── evals/                   public test sets and scorers
```

## 4. Data model

Every table has `tenant_id`, protected by Postgres row-level security. Nothing is edited in place: a change is a new version row, which gives the audit trail for free.

```sql
-- Platform (shared) ---------------------------------------------------------
tenant, app_user, role_binding              -- roles: admin | author | reviewer | approver | viewer
document      (id, title, file_type, s3_key, sha256, status,         -- any source file
               source_system, source_id, source_version, source_url, synced_at)  -- where it came from; 'upload' if manual
connector     (tenant_id, system, scope, secret_ref, last_sync_at)  -- one per connected client system
page          (document_id, page_no, ocr_confidence, render_s3_key)
table_extract (document_id, page_no, cells jsonb)                     -- exact grids from PDF, Word, Excel, RTF
chunk         (document_id, section_path, text, page, bbox, embedding vector)
fact          (subject_key, value, unit, version)                     -- 'product.strength' = '10 mg'; one value, reused everywhere
template      (key, version, spec jsonb)                              -- 'ctd.us.3.2.P.5', sections + slots
run, run_step                                                         -- every agent run and step, with model + prompt version
claim         (run_id, target_id, text, status)                       -- unverified | verified | rejected | human_confirmed
citation      (claim_id, chunk_id, page, bbox, quote, match_score)
check_result  (claim_id, check, verdict)                              -- quote | number | support | consistency
review_action, signature                                              -- approve / edit / reject; e-signature with meaning + content hash
audit_log     (actor, action, target, before, after, at, hash)        -- append-only, hash-chained

-- CTD/eCTD ------------------------------------------------------------------
product       (name, inn, dosage_form, strength, product_class)       -- small_molecule | biologic
application   (product_id, authority, app_type, format,               -- format: ctd_pdf | ectd_3_2_2 | ectd_4_0
               profile_version, app_number)
section       (application_id, ctd_code, template_version, status)    -- '3.2.P.5.1'; empty | drafting | in_review | approved
section_version (section_id, version, content jsonb, source_kind)     -- source_kind: ai_draft | human | uploaded
section_dependency (upstream_section_id, downstream_section_id)       -- 3.2 -> 2.3, 5.3.5 -> 2.7 -> M1 labeling
submission_doc (id uuid, section_version_id | document_id, pdf_s3_key, md5, sha256)  -- a file exists once
sequence      (application_id, number, submission_type, status)
placement     (sequence_id, submission_doc_id, ctd_code,
               v3_operation, v3_replaces_id,                          -- eCTD 3.2.2: new | replace | append | delete
               v4_context_of_use, v4_keywords, v4_replaces_id, v4_status)  -- eCTD 4.0: active | suppressed
study         (application_id, study_code, study_type)                -- drives US Study Tagging Files
validation_run (sequence_id, format, rules_version, errors jsonb)

-- Gap analysis (Phase 6) --------------------------------------------------------
engagement, rule_assessment, finding, gap_report
```

The split between `submission_doc` (the file) and `placement` (where it sits in one sequence) is what lets one data model serve CTD PDF, eCTD 3.2.2 and eCTD 4.0.

## 5. Region and format engine

One YAML **profile per authority** in `products/ectd/profiles/` holds everything that differs by country: allowed formats and dates, application types, required sections per type, Module 1 structure, templates to use, and validation rule versions. A `FormatPolicy` function reads it and answers one question — *which formats are allowed for this authority, application type and situation, and why?* The wizard, the API and the publisher all ask it, so an invalid combination can't be created anywhere.

```yaml
authority: US-FDA
formats:
  ectd_4_0:   {allowed_for: [new_application], since: 2024-09-16}
  ectd_3_2_2: {allowed_for: [new_application, existing_3_2_2_application]}
  ctd_pdf:    {allowed_for: [], reason: "eCTD required for NDA, ANDA, BLA, commercial IND"}
application_types: [nda_505b1, nda_505b2, anda, bla_351a, bla_351k]
module1: us_regional          # forms 356h/1571, PLR labeling + SPL
```

**Format status by authority (mid-2026; re-check the agency's own site before each release):**

| Authority               | CTD PDF                                | eCTD 3.2.2                                      | eCTD 4.0                                                                                                                                                   |
| ----------------------- | -------------------------------------- | ----------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| US FDA                  | Not for NDA, ANDA, BLA, commercial IND | Yes; required for applications already in 3.2.2 | New applications since 16 Sep 2024 ([FDA](https://www.fda.gov/drugs/electronic-regulatory-submission-and-review/electronic-common-technical-document-ectd)) |
| EU, EMA centralised     | No                                     | Yes                                             | Optional for new applications since 22 Dec 2025; mandatory expected 2027                                                                                   |
| EU, national procedures | Some still take NeeS                   | Yes                                             | Not yet                                                                                                                                                    |
| Japan PMDA              | No                                     | Only for dossiers started before 1 Apr 2026     | Mandatory for new applications since 1 Apr 2026                                                                                                            |
| Health Canada           | Check per submission type              | Yes                                             | Optional from 2026, mandatory announced for 2028                                                                                                           |
| Other countries         | Often CTD as PDF                       | Varies                                          | Mostly not yet                                                                                                                                             |

**Application types and what they change:**

| Type                 | US            | EU                | Effect on sections                                                    |
| -------------------- | ------------- | ----------------- | --------------------------------------------------------------------- |
| New drug             | NDA 505(b)(1) | Art. 8(3)         | Full M2–M5                                                           |
| Known drug, new form | NDA 505(b)(2) | Art. 10(3) hybrid | Literature and bridging sections; reference product in M1             |
| Generic              | ANDA          | Art. 10(1)        | Bioequivalence (5.3.1.2) instead of efficacy trials; reduced M4/M5    |
| Biologic             | BLA 351(a)    | Full MAA          | Biotech content in 3.2.S (ICH Q5 series); 3.2.A.2 adventitious agents |
| Biosimilar           | BLA 351(k)    | Art. 10(4)        | Comparability to the reference product across M3–M5                  |

Build the US profile first (Phase 2), EU and Japan in Phase 5. Only the FDA dates above come from the agency's own page; confirm the rest on EMA, PMDA and Health Canada sites.

## 6. Ingestion

Every uploaded file becomes pages, exact tables and searchable chunks, each remembering its page and position so a citation can point back to it.

| Source                               | How                       | Notes                                                                          |
| ------------------------------------ | ------------------------- | ------------------------------------------------------------------------------ |
| PDF with text                        | PyMuPDF                   | Native text is always more accurate than OCR                                   |
| Scanned PDF, or any page with tables | Docling                   | Low-confidence numbers flag the page for a human fix before it can be cited    |
| Word                                 | Docling                   | Keeps headings and tables                                                      |
| Excel / CSV                          | pandas                    | Straight into exact tables — stability data, batch results, LIMS exports      |
| RTF tables and listings              | LibreOffice → PDF + text | Clinical output tables kept as grids                                           |
| SAS datasets, define.xml             | Metadata only             | Placed in Module 5 and checked for presence; the platform doesn't analyse them |

Chunks follow the document's own section structure; a table is never split mid-row. Search combines meaning (vectors) and keywords, filtered to the application and to the sources a template allows.

**Connectors — getting data out of client systems.** Pharma data lives in systems, not loose files, so connectors are a platform layer (the bottom layer on the main tab's diagram). Every connector implements one interface in `platform/connectors/`:

```python
class Connector(Protocol):
    def list(self, since: datetime | None) -> Iterator[SourceItem]  # new or changed items only
    def fetch(self, item_id: str) -> SourceFile                     # file + metadata
    def link(self, item_id: str) -> str                             # deep link back to the source record
    # later: push(file, metadata) -> str                            # write an approved output back
```

Rules: **read-only first**; every fetched file keeps its source system, ID, version and link, so a citation points back to the client's system of record; syncs are incremental; the connector uses a client-created service account limited to the folders or binders they choose; credentials sit in the secrets manager; every sync is in the audit log.

| Source                    | Examples                                                                    | What we pull                                           | How                                                                                                                     | When                                                                                             |
| ------------------------- | --------------------------------------------------------------------------- | ------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| Manual                    | PDF, Word, Excel, RTF, zip folders                                          | Anything                                               | Upload, bulk zip                                                                                                        | Phase 1                                                                                          |
| Existing eCTD dossiers    | Exports from Lorenz docuBridge, EXTEDO eCTDmanager, Veeva Vault Submissions | Prior sequences                                        | Import the sequence folders: parse`index.xml` and regional XML, rebuild sequences, placements and the current dossier | Phase 2 — without this, an existing application's next sequence can't reference prior documents |
| File shares               | SharePoint / OneDrive, Google Drive, Box                                    | Word, Excel, PDF                                       | Microsoft Graph and Drive APIs                                                                                          | Phase 3                                                                                          |
| LIMS                      | LabWare, LabVantage, STARLIMS                                               | Stability and batch results                            | Scheduled CSV/Excel export first; API later                                                                             | Phase 3                                                                                          |
| Document management / RIM | Veeva Vault (RIM, QualityDocs), OpenText Documentum, other RIM suites       | Source documents, prior submissions, registration data | Vault REST API (queries + document export); others via their APIs or exports                                            | Phase 4, Vault first                                                                             |
| QMS                       | Veeva Vault QMS, MasterControl, TrackWise                                   | SOPs, deviations, CAPAs, change controls               | API or scheduled export                                                                                                 | Phase 6, for gap analysis                                                                        |

**When a client won't let a cloud service connect in:** they export on a schedule to an S3 or SFTP drop folder that the platform watches; an on-premises sync agent can come later.

**Cost:** eCTD import about 1 week, SharePoint about 1 week, Veeva Vault about 2 weeks — roughly 4 weeks on top of the 40-week plan. Build each only when a design partner needs it; manual and bulk upload work for every pilot.

## 7. Authoring engine

Every section, in every module and region, is drafted the same way: a **template** says what the section needs, and the **drafter agent** fills it from the application's sources.

**Templates.** One YAML file per section and region variant, whose structure follows ICH M4 (M4Q, M4S, M4E) and the region's Module 1 specification, and whose content follows the guidelines listed below for that section. Each template lists **slots**: what each part must say, which sources may fill it, and whether it's required.

**Guidelines behind the templates.** ICH M4 only says *where* content goes. What each section must contain comes from many more sources, so every template slot carries the guidelines (and versions) it must satisfy. These guideline texts are ingested like any source: the drafter can cite them, and the cross-validator checks required elements (for example, a stability section must cover the storage conditions ICH Q1A requires).

| Area                    | Guidelines and standards                                                                                                                                                                                                                                                                                                                                     |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Structure (all modules) | ICH M4 (M4Q, M4S, M4E); region Module 1 specs; ICH M8 (eCTD); FDA PDF and eCTD technical specifications                                                                                                                                                                                                                                                      |
| M3 Quality              | ICH Q1A–Q1E stability (a consolidated Q1 revision is in draft), Q2(R2) and Q14 analytical procedures, Q3A–Q3D impurities, M7 mutagenic impurities, Q6A/Q6B specifications, Q8(R2) development, Q9(R1) risk, Q11 drug substance, Q12 lifecycle, Q13 continuous manufacturing; Q5A–Q5E for biologics; USP, Ph. Eur. and JP monographs for the chosen region |
| M4 Nonclinical          | ICH M3(R2) timing; S1 carcinogenicity, S2 genotoxicity, S3 toxicokinetics, S4 chronic toxicity, S5 reproductive, S6 biotech products, S7A/S7B safety pharmacology, S8 immunotoxicity, S9 oncology, S10 phototoxicity, S11 paediatric; GLP                                                                                                                    |
| M5 Clinical             | ICH E3 study reports, E6(R3) GCP, E9 and E9(R1) statistics and estimands, E2A/E2F safety, E4 dose-response, E5 ethnic factors, E7 geriatrics, E11 paediatrics, E14 QT; for generics M13A bioequivalence and M9 BCS biowaivers; CDISC SDTM/ADaM and FDA's Study Data Technical Conformance Guide for datasets                                                 |
| M1 and labeling         | US: 21 CFR 314 (NDA/ANDA content), 21 CFR 601 (BLA), 21 CFR 201.56/201.57 (PLR labeling), SPL; FDA product-specific guidances for generics. EU: Notice to Applicants, QRD templates, EMA scientific guidelines. Japan: MHLW/PMDA notifications                                                                                                               |

The guideline list and versions live in the region profile and template files, not in code, and are reviewed like any rule change: ICH revises these regularly (E6(R3) was finalised in January 2025; M4Q and Q1 revisions are in progress), so confirm current versions on ich.org and each agency's site.

**Six slot kinds — who writes each:**

| Slot kind            | Written by                                 | Example                                          |
| -------------------- | ------------------------------------------ | ------------------------------------------------ |
| `form_field`       | Code, from the fact store                  | FDA 356h fields, EU application form             |
| `boilerplate`      | Template text                              | Standard guideline statements                    |
| `structured_table` | Code, from parsed data                     | Batch analyses, specifications, stability tables |
| `fact`             | AI extracts a value + exact quote          | Dose, shelf life, assay method                   |
| `table_summary`    | AI describes a table; every number checked | Describing efficacy results                      |
| `narrative`        | AI writes from checked facts only          | Discussion, overviews                            |

**Agents:**

&#91;embedded content: authoring flow · planner, per-section drafter, cross-validation, publishing\]

- **Planner** — from authority + application type, lists the required sections (from the region profile and knowledge graph) and the order to draft them. A human confirms.
- **Drafter** (one run per section) — find sources → extract facts with exact quotes → check them → write prose around the checked facts → check every sentence again → hand to a human. Facts are inserted as locked tokens the AI can place but not change. Anything unsourced becomes a yellow gap.
- **Cross-validator** — Section 8.

**Citation checks** (code, run before a human sees anything):

1. **Quote exists** in the cited source (exact or near-exact text match).
2. **Numbers and units match** the quote or the source table exactly.
3. **The quote supports the claim** — a separate AI call with no drafting context judges it.
4. **Consistent with stored facts** and other sections.

A sentence that fails 1 or 2 is dropped; failing 3 marks it for attention. No agent can skip these steps.

**What each module needs:**

| Module | Main slot kinds                                     | Special output                                          |
| ------ | --------------------------------------------------- | ------------------------------------------------------- |
| M1     | `form_field`, `boilerplate`, `fact`           | US labeling as SPL XML; EU SmPC/PIL on the QRD template |
| M2     | `table_summary`, `narrative`                    | Drafted last, from the approved M3–M5                  |
| M3     | `structured_table`, `fact`                      | Small-molecule, biologic and generic variants           |
| M4     | `fact`, `table_summary`                         | Usually uploaded as-is from CROs                        |
| M5     | `fact`, `table_summary`, per-patient narratives | Study Tagging Files (US 3.2.2); datasets placed         |

## 8. Cross-validation

Runs on demand and automatically before every package build. Each mismatch opens a review task pointing at both locations.

| Check                          | How                                                                         | Example                                                                       |
| ------------------------------ | --------------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| Same fact, same value          | Code: every mention of a fact across M1–M5 is compared with the fact store | Strength says 10 mg in 3.2.P.1 but 20 mg in the prescribing information       |
| Summary matches source         | Citation checks run across modules                                          | A number in 2.7.3 that isn't in the cited M5 study report                     |
| Labeling matches clinical data | AI compares labeling statements with 2.7 and M5, then citation checks       | Adverse reaction rate in labeling differs from the study report               |
| Nothing out of date            | `section_dependency` graph                                                | 3.2.P.8 stability changed after 2.3 was approved → 2.3 flagged for re-review |
| Nothing missing                | Region profile + application type                                           | Generic without a bioequivalence study report in 5.3.1.2                      |

Flagged sections get a re-draft suggestion; nothing is changed automatically.

## 9. Review, sign-off, Word round-trip

- **Review screen:** draft on the left, source PDF on the right; clicking a sentence highlights its quote. Each sentence shows verified, needs attention, or human-confirmed.
- **Approval** is per section, never "approve all". A section with an open gap or failed check can't be approved.
- **E-signature** asks the user to re-authenticate, and records who, when, what it means (authored, reviewed, approved) and a hash of the exact content. Only signed sections can be published.
- **Word round-trip:** any section exports to `.docx` on the client's own template (citations as comments, facts as locked fields). An edited file uploaded back is compared with the stored version; changes become tracked human edits, and changed factual sentences are re-checked.
- **Audit log:** every action by a person or an agent, append-only.

## 10. Publishing and technical validation

Publishing is plain code — no AI. Approved sections render to PDF (LibreOffice, then pikepdf adds bookmarks and links, embeds fonts and removes security settings, per the FDA PDF specification). One publisher per format, all reading the same `submission_doc` and `placement` tables:

|                           | CTD PDF                                               | eCTD 3.2.2                                                                                     | eCTD 4.0                                                         |
| ------------------------- | ----------------------------------------------------- | ---------------------------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| Output                    | One bookmarked PDF per module + CTD table of contents | Folder tree (m1–m5),`index.xml`, regional M1 XML (`us-regional.xml`, `eu-regional.xml`) | One XML message covering M1–M5                                  |
| Where a document goes     | CTD heading                                           | Leaf under a fixed CTD heading                                                                 | A "context of use" with controlled-vocabulary codes and keywords |
| Changing a document later | Tracked internally                                    | Leaf operation: new, replace, append, delete                                                   | Replace or suppress the context of use                           |
| Reusing a document        | Copy                                                  | Copy per sequence                                                                              | Referenced by ID across sequences and applications               |
| Study documents           | —                                                    | Study Tagging Files (US)                                                                       | Keywords on the context of use                                   |
| Checksums                 | —                                                    | MD5                                                                                            | SHA-256                                                          |
| Validation                | Bookmarks, links, fonts, no security                  | DTDs + the region's validation criteria                                                        | XML schemas + controlled vocabularies + regional rules           |

**Both eCTD formats** get sequence numbering, the current-dossier view (which documents are live after all replacements), a validation report before export, and a zip package for upload to the agency gateway. Direct gateway submission (FDA ESG, EU CESP) comes after the pilots.

**Moving an application from 3.2.2 to 4.0** is an explicit, reviewed action, offered only when the authority supports it; FDA doesn't yet.

## 11. FDA gap analysis (Phase 6)

Reuses ingestion, search, citation checks, the agent runtime, review and the audit log unchanged. New work:

- **GMP knowledge graph** in Neo4j: 21 CFR 211 and ICH Q7 split into individual requirements, each linked to the evidence it needs (SOP, batch record, validation report) and to the FDA 483 citations and warning letters that cite it. Citations come from the [FDA Data Dashboard API](https://datadashboard.fda.gov/oii/api/api-definitions-citations.htm) (not openFDA); warning letters from fda.gov.
- **Gap assessor agent**, one branch per requirement:

&#91;embedded content: gap-analysis agent · rules checked in parallel, verified, then confirmed by a human\]

- **Report:** each finding shows the requirement, the quoted evidence from the client's own documents (or what's missing), severity, and similar FDA 483s as precedent. A finding without a verified quote is never shown.

## 12. Frontend

| Screen                 | What the user does                                                                                                 |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------ |
| New application wizard | Pick authority → application type → format; disabled options show why                                            |
| Dossier tree           | See M1–M5 with each section's status: empty, drafting, in review, approved, outdated                              |
| Sources                | Upload files; see parsing status; fix flagged OCR numbers                                                          |
| Section editor         | Edit the draft with locked facts and citation chips; source PDF alongside; start a draft; export or re-import Word |
| Cross-validation       | List of mismatches, each linking to both locations                                                                 |
| Review queue           | Sections waiting for me; approve, reject or request changes; sign                                                  |
| Sequences              | Build a sequence, see lifecycle and current dossier, run validation, download the package                          |
| Gap analysis (Phase 6) | Set up an engagement, see findings by requirement, sign the report                                                 |

Key components: the source-side-by-side viewer (react-pdf with highlight boxes), the TipTap editor with custom nodes for facts, citations and gaps, and a live progress panel fed by the API over server-sent events. Types are generated from the API, so frontend and backend can't drift.

## 13. Infra, security, CI

- **Environments:** local (Docker Compose), staging (one VM, public data only), production (one VM, managed Postgres with point-in-time recovery, S3 with versioning).
- **Deploy:** GitHub Actions builds images, runs database migrations, then restarts containers.
- **CI:** lint + type checks, tests against a real Postgres, the platform/product import rule, and the eval suite on any change to prompts, agents or checks — a drop in scores fails the build.
- **Security:** row-level security per client, files under per-client S3 prefixes with short-lived links, secrets in a secrets manager, Claude under zero-data-retention terms, nightly backups with a monthly restore test.
- **Part 11-ready from day one:** unique users, e-signatures with re-authentication, append-only audit log, versioned records. Formal GxP validation and SOC 2 come after the pilots.

## 14. Testing with public data

Each test uses public material where the right answer is already known, or makes one by inserting known errors. Tests live in `evals/` and run in CI.

| Capability       | Public data                                                                                                                                                                             | Method                                                                                                                                                          | Pass bar                                                              |
| ---------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------- |
| OCR              | EPAR pages, rendered to images and degraded                                                                                                                                             | Their native text is the answer key                                                                                                                             | ≤ 1% character errors clean, ≤ 3% degraded                          |
| Tables           | DailyMed SPL labels (tables in XML)                                                                                                                                                     | Render to PDF, extract, compare cell by cell                                                                                                                    | 99.5% exact; every wrong cell flagged                                 |
| Citation checks  | True claims from EPARs, then altered (number, unit, drug, negation)                                                                                                                     | Do altered claims get rejected?                                                                                                                                 | 100% of number/unit changes; ≥ 90% of others; ≤ 5% false rejections |
| eCTD 3.2.2       | FDA specifications and example submissions                                                                                                                                              | Validate with[Lorenz eValidator Basic](https://www.lorenz.cc/solutions/eValidator-basic/) (free, US profile); compare its error codes with ours on seeded errors | 0 high-severity errors; ≥ 95% agreement                              |
| eCTD 4.0         | ICH M8 implementation package; FDA, EMA, PMDA regional guides                                                                                                                           | Same content published in 3.2.2 and 4.0                                                                                                                         | Both valid; same current dossier                                      |
| M3 drafting      | EPAR quality sections, Drugs@FDA chemistry reviews, synthetic batch and stability data                                                                                                  | Tables vs data; facts vs reference summary                                                                                                                      | Tables 100% exact; ≤ 2% unsupported sentences                        |
| M2 / M5 drafting | [EMA clinical data publication](https://www.ema.europa.eu/en/human-regulatory-overview/marketing-authorisation/clinical-data-publication): study reports + the sponsor's own 2.5 and 2.7 | Draft from the reports; compare with the sponsor's summaries                                                                                                    | ≥ 80% of the sponsor's facts; ≤ 2% unsupported                      |
| Labeling + SPL   | DailyMed                                                                                                                                                                                | Regenerate SPL; compare with the published one                                                                                                                  | Schema-valid; same content                                            |
| Cross-validation | DailyMed label + EPAR SmPC with inserted mismatches                                                                                                                                     | Count mismatches caught                                                                                                                                         | ≥ 95% caught; ≤ 1 false alarm per 10 sections                       |
| Gap analysis     | [FDA Data Dashboard](https://datadashboard.fda.gov/oii/cd/inspections.htm) 483 citations, warning letters → synthetic records with planted gaps                                         | Does the agent flag the section FDA cited?                                                                                                                      | ≥ 85% recall, ≥ 90% precision                                       |

Check the EMA portal's terms of use before using it for a commercial benchmark. Handwritten records, company writing style and reviewer trust can only be tested with design partners.

## 15. Build plan, week by week

Same six phases and gates as the main tab. A phase starts only when the previous gate passes.

| Weeks                                               | Build                                                                                                                      | Done when                                                                     |
| --------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| **Phase 1 — Foundations**                    |                                                                                                                            |                                                                               |
| 1                                                   | Repo, Docker Compose, CI, Clerk login, tenants + row-level security, audit log                                             | Tenant A can't read tenant B's data (test)                                    |
| 2                                                   | Upload to S3, PDF parsing, pages, chunks, search                                                                           | 50 public EPARs searchable                                                    |
| 3                                                   | OCR for scans and tables; Word, Excel, RTF parsing; OCR correction screen                                                  | Scanned FDA 483 PDFs parsed with tables intact                                |
| 4                                                   | Claude gateway + Langfuse; citation checks 1–2                                                                            | **Gate 1:** citations land on the exact page; fake quotes 100% rejected |
| **Phase 2 — Setup + publishing**             |                                                                                                                            |                                                                               |
| 5                                                   | Product, application, section tables; US profile; FormatPolicy; wizard                                                     | Only valid combinations can be created                                        |
| 6                                                   | Dossier tree; place uploaded documents in sections; PDF renderer                                                           | A dossier of uploaded documents renders                                       |
| 7–8                                                | eCTD 3.2.2 publisher: folders,`index.xml`, `us-regional.xml`, leaf lifecycle, MD5, Study Tagging Files                 | Sequences 0000 and 0001 build                                                 |
| 9                                                   | CTD PDF publisher; technical validation; current-dossier view                                                              | Both formats export                                                           |
| 10                                                  | Sequence screens, package download                                                                                         | **Gate 2:** eValidator 0 high-severity errors → start design partners  |
| **Phase 3 — Authoring core**                 |                                                                                                                            |                                                                               |
| 11                                                  | Agent runtime (checkpoints, pause/resume, live progress); citation checks 3–4                                             | A run survives a restart and resumes                                          |
| 12                                                  | Knowledge graph: required sections per application type; planner agent                                                     | Planner output matches the US profile for all 5 types                         |
| 13                                                  | Template engine, fact store;`form_field`, `boilerplate`, `structured_table`                                          | Tables built from data, exact                                                 |
| 14–15                                              | Drafter agent (`fact`, `table_summary`, `narrative`); section editor; review + e-signature                           | One section drafted, reviewed and signed end to end                           |
| 16–17                                              | M3 templates (small molecule + generic); M1 US forms and cover letter                                                      | Full 3.2.P drafted from synthetic data                                        |
| 18                                                  | M2.3 quality summary; eval run                                                                                             | **Gate 3:** M3 tables 100% exact, ≤ 2% unsupported sentences           |
| **Phase 4 — Full M1–M5 + cross-validation** |                                                                                                                            |                                                                               |
| 19–20                                              | M5 study-report templates (ICH E3), output-table summaries, patient narratives                                             | Study-report sections from EMA public reports                                 |
| 21                                                  | M4 templates; M2.4–2.7                                                                                                    | Clinical summary drafted from approved M5                                     |
| 22                                                  | US labeling (PLR) + SPL generator                                                                                          | SPL schema-valid                                                              |
| 23–24                                              | Cross-validator + dependency graph                                                                                         | Stale sections flagged after an upstream change                               |
| 25                                                  | Word round-trip                                                                                                            | Edited Word file re-imports with tracked changes                              |
| 26                                                  | Eval run                                                                                                                   | **Gate 4:** ≥ 95% mismatches caught; M2/M5 bars met                    |
| **Phase 5 — eCTD 4.0 + regions**             |                                                                                                                            |                                                                               |
| 27–30                                              | eCTD 4.0 publisher: message, controlled vocabularies, context-of-use lifecycle, document reuse, SHA-256, schema validation | A 4.0 sequence builds and validates                                           |
| 31                                                  | EU profile (EMA Module 1, SmPC/PIL); Japan profile (4.0 publishing — Japanese-language authoring not included)            | Wizard offers EU and Japan correctly                                          |
| 32                                                  | Round-trip test                                                                                                            | **Gate 5:** same content valid as 3.2.2 and 4.0                         |
| **Phase 6 — FDA gap analysis**               |                                                                                                                            |                                                                               |
| 33–35                                              | GMP knowledge graph; FDA Data Dashboard sync                                                                               | Every 21 CFR 211 section cited in the last 5 years is linked                  |
| 36                                                  | Benchmark: synthetic records with planted gaps                                                                             | Scorer runs in CI                                                             |
| 37–38                                              | Gap assessor agent                                                                                                         | Full run on the benchmark                                                     |
| 39–40                                              | Gap screens + signed report                                                                                                | **Gate 6:** ≥ 85% recall, ≥ 90% precision                             |
