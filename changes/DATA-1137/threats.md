# Threat Analysis: DATA-1137

Reviewer: blossom-security (automated)
Inputs:   changes/DATA-1137/plan.md, changes/DATA-1137/spec.md
Date:     2025-01-31

## Overall risk level

**Medium**

This ticket is a pure read-only analytics pipeline — no endpoints, no financial mutations,
no raw PII ingested, no external network calls. The risk driver is not the computation itself
but three specific surface areas that require explicit controls: (1) `tests/fixtures/golden_set.csv`
being committed to git, which must provably contain synthetic data only; (2) multi-tenancy
isolation that is implicitly delegated upward to the caller — model.py propagates
`idclient/idcompany/idaccount` without re-filtering, meaning the data contract from
`prepare_smart_budget_data()` must be the sole tenant gate, especially before DATA-1140
activates the public endpoint; and (3) a new external dependency (`statsmodels>=0.14.0`)
added without a pinned upper bound, creating a supply-chain window. No category exceeds Medium
in isolation, and there are no irreversible operations, PAN/CVV fields, or compliance-impacting
mutations in scope.

---

## Category review

### 1. Authentication surface — Low

- No new public or internal endpoints are introduced in this ticket (DATA-1140 is explicitly
  out of scope per plan, DCR D-02 note and JSON contract section).
- No new authentication flows, MFA changes, or session modifications.
- No new service-to-service trust relationships — `model.py` and `scripts/run_methods.py`
  are pure local computation modules with no API client code.
- The CLI (`scripts/run_methods.py`) is an internal analyst tool; it does not accept tokens,
  sessions, or credentials.

**Recommendations:**
- None for this ticket. DATA-1140 (endpoint activation) must undergo its own auth surface
  review before `compute_budget_suggestions()` is reachable from outside the process.

---

### 2. Authorization — Low

- No RBAC changes, no new roles, no permission expansions.
- Multi-tenancy: plan (§ Restricciones) states `model.py` propagates `idclient/idcompany/idaccount`
  "sin filtrar" — by design, because tenant filtering is the responsibility of the caller via
  `prepare_smart_budget_data()`. This is architecturally correct for a library module but
  creates a latent risk if `compute_budget_suggestions()` is ever called with an unfiltered
  or cross-tenant DataFrame.
- The CLI `--input` flag accepts an arbitrary file path with no access control — appropriate
  for an internal batch tool, but must not be exposed to untrusted callers.

**Recommendations:**
- Add a docstring note to `compute_budget_suggestions()` explicitly stating: "Caller is
  responsible for ensuring the input DataFrame is pre-filtered to a single tenant. This
  function does not enforce tenant isolation." This makes the trust contract explicit for
  DATA-1140 implementers.
- When DATA-1140 is designed, mandate that the API layer verifies session ownership of
  every `idaccount` in the DataFrame before passing it to this function.

---

### 3. PII / PAN / CVV / SSN — Medium

- The DataFrame flowing through the pipeline carries `idclient`, `idcompany`, and `idaccount`
  — account-level identifiers that are pseudonymous PII in a credit union context (they can
  be resolved to a member's identity via the core system).
- `monthly_total` is aggregated spending — derived analytics, not raw transaction detail.
  Lower sensitivity than raw amounts, but still member behavioral data.
- **Golden set concern (highest PII risk in this ticket):** spec T3.1 generates
  `tests/fixtures/golden_set.csv` from `data/dough/test/query/smart_budget_synthetic.csv`
  and commits it to the repo. The CSV includes `idaccount`, `idclient`, `idcompany`,
  and `suggested_amount` columns (spec T3.1 column list). If synthetic IDs happen to
  collide with real member identifiers — or if the wrong source CSV is used at generation
  time — real member spending patterns could be permanently embedded in git history.
- Structlog logging is scoped correctly per plan: method, treatment, n_buckets,
  n_suggestions, n_null_suggestions. **No member identifiers are logged** — this is correct.
- No PAN, CVV, SSN, DOB, or card data is in scope. The `category_id` and `defaultcategory`
  fields are category labels, not member-identifying data.
- No URL paths or query strings carry PII — the pipeline is in-process only.
- CLI `--output` writes JSON including `idclient/idcompany/idaccount` to a file or stdout.
  If used on a shared machine, this output file must not be world-readable.

**Recommendations:**
- Before generating golden_set.csv (T3.1), the implementer must explicitly confirm the
  source file is the synthetic dataset and log the SHA-256 of the source CSV in the commit
  message for traceability.
- Add a `.gitattributes` or repo note stating that `tests/fixtures/golden_set.csv` must
  never be regenerated from non-synthetic source data.
- The spec (T3.1) uses `/tmp/golden_raw.json` as the intermediate file path. On multi-user
  Linux systems, `/tmp` is world-accessible. Use a mktemp-style approach or the current
  user's home directory for the intermediate file instead.

---

### 4. Trust boundary — Low

- No inbound webhooks, no outbound HTTP calls — all computation is local and in-memory.
- `statsmodels.tsa.holtwinters.ExponentialSmoothing` processes member spending series
  in-process; no data is transmitted externally.
- The CLI crosses one trust boundary: filesystem reads (`--input` CSV) and optional
  filesystem writes (`--output` JSON). Both are within the analyst's environment.
- Input validation at the boundary: `apply_treatment()` raises `ValueError` on invalid
  treatment codes (spec); `compute_budget_suggestions()` raises `ValueError` on invalid
  method names (spec); `compute_holt_winters()` raises `ValueError` on series < 3 (spec).
  This is sufficient for a library module.
- The CLI `--input` flag does not validate that the path is within an expected data
  directory — arbitrary filesystem paths are accepted. This is low risk for internal tooling
  but should be noted if the CLI is ever wrapped in a web interface.

**Recommendations:**
- None blocking for this ticket.

---

### 5. Persistence & data stores — Medium

- No new databases, tables, or columns introduced.
- No new caches, queues, or blob stores.
- **New persistent artifact: `tests/fixtures/golden_set.csv` committed to git.** Git history
  is effectively permanent and immutable — if PII enters this file, it cannot be cleanly
  removed without a full git history rewrite. This is the primary persistence risk in the
  ticket (see Category 3 for controls).
- `requirements.txt` is modified to add `statsmodels>=0.14.0`. No upper-bound pin is
  specified, meaning `pip install -r requirements.txt` could pull a future breaking or
  compromised patch version. Supply chain risk is low for statsmodels (mature library,
  no historical compromise events) but a pinned range is standard practice.
- Computation output is ephemeral (JSON to stdout or a local file). No retention policy
  is needed for the computation itself.
- No right-to-deletion or right-to-export obligations arise from the model outputs directly,
  but golden_set.csv (if it contained real member IDs) would be subject to CCPA/GLBA
  deletion obligations — another reason to enforce synthetic-only.

**Recommendations:**
- Pin statsmodels to a bounded range: `statsmodels>=0.14.0,<0.15.0` (or use a
  `requirements.lock` / pip-tools hash pinning). This prevents silent upgrades between
  minor versions that could change numerical results or introduce regressions.
- Consider adding `tests/fixtures/golden_set.csv` to `.gitattributes` with `export-ignore`
  so it is excluded from source archives sent to third parties.

---

### 6. Audit trail — Low

- This ticket introduces no financial mutations. `compute_budget_suggestions()` is a
  pure read-only computation — it does not post, transfer, fee, or modify any member
  account data.
- Suggestions are advisory output only; no mutation occurs until a member or the system
  acts on them (out of scope for this ticket).
- Structlog operational logging is defined (plan § Restricciones): method, treatment,
  n_buckets, n_suggestions, n_null_suggestions. This is appropriate for an analytics pipeline.
- No `logger.audit(...)` entries are required for read-only suggestions computation per
  Blossom's baseline (audit log is reserved for financial mutations and sensitive data
  access changes).

**Recommendations:**
- None for this ticket. When DATA-1140 exposes this function via an endpoint, audit logging
  for "member requested budget suggestion" should be considered at the API layer.

---

### 7. Idempotency & concurrency — Low

- The pipeline is purely deterministic and stateless: same DataFrame + same parameters →
  same output. Natural idempotency is inherent.
- No shared state, no database writes, no queue publishes — concurrency is not a concern
  for this library module.
- No compensating transactions needed (no mutations).
- The CLI is designed for sequential batch invocation; no parallel execution concern.

**Recommendations:**
- None.

---

### 8. Secrets & credentials — Low

- No new secrets, API keys, JWT signing keys, or DB credentials are introduced.
- `statsmodels` is a pure local computation library with no external API calls or credential
  requirements.
- The CLI reads CSV files from the local filesystem; no credentials are passed.
- No `.env` files or secrets appear in the plan or spec.

**Recommendations:**
- None.

---

### 9. Rate limiting & abuse — Low

- No new endpoints are introduced in this ticket.
- The CLI is an internal batch tool — not exposed to external users.
- No rate limiting is needed for a local analytics script invoked by analysts.
- If `compute_budget_suggestions()` is called with a very large DataFrame (many members ×
  categories × months), Holt-Winters fitting via statsmodels could be CPU-intensive. This
  is an operational concern (not a security concern) and scoped to DATA-1140's API design.

**Recommendations:**
- None for this ticket. DATA-1140 must evaluate whether the endpoint needs per-member
  rate limiting given that HW fitting is O(n × buckets).

---

### 10. BSA/AML & compliance — Low

- This ticket introduces no transaction monitoring logic, no CTR/SAR workflow changes, and
  no modifications to compliance artifact retention.
- The model output is advisory budget suggestions derived from aggregated monthly spending —
  it does not itself constitute a reportable event.
- `monthly_total` is already aggregated and clamped to ≥ 0 upstream in `aggregate_monthly()`;
  the model layer never sees raw transaction amounts.
- The `display_label` and `reason` fields are member-facing copy strings — no compliance
  content.
- Access to the computation is currently limited to internal analysts running the CLI.
  No regulatory access gate is needed at this layer.

**Recommendations:**
- None for this ticket. If budget suggestions are later stored and used for member
  profiling or shared with third parties, a privacy impact assessment (GLBA Safeguards
  Rule, state UDAP) would be required at that point.

---

## Mandatory controls for this change

These are non-negotiable requirements that must be satisfied before the ticket is merged.

- [ ] **Golden set must be synthetic:** Before running T3.1, the implementer must confirm
  that `data/dough/test/query/smart_budget_synthetic.csv` contains no real member
  identifiers (`idclient`, `idcompany`, `idaccount`). The commit message for
  `golden_set.csv` must include the SHA-256 hash of the source CSV (e.g.,
  `sha256: <hash> of smart_budget_synthetic.csv`) to prove provenance.
- [ ] **No member IDs in structlog output:** Verify that every `logger.*` call in
  `model.py` and `run_methods.py` logs only aggregate counts (n_buckets, n_suggestions,
  n_null_suggestions) and method parameters — never individual `idclient`, `idcompany`,
  or `idaccount` values.
- [ ] **statsmodels version bounded:** `requirements.txt` must specify
  `statsmodels>=0.14.0,<0.15.0` (not open-ended `>=0.14.0`) to prevent silent
  numerical regressions from future minor-version changes.
- [ ] **apply_treatment() must not mutate the original DataFrame:** Confirmed by test
  `test_apply_treatment_does_not_mutate_original` (spec T1.2) — this test must pass.
- [ ] **Negative forecast clamping enforced:** `compute_holt_winters()` and
  `compute_budget_suggestions()` must clamp negative results to `0.0` before rounding.
  Confirmed by `test_compute_holt_winters_clamps_negative` (spec T1.5).
- [ ] **Invalid method/treatment raises ValueError, not silent failure:** Confirmed by
  `test_apply_treatment_invalid_raises` and the ValueError contract on
  `compute_budget_suggestions()` for invalid method strings. These tests must pass.
- [ ] **reason field absent when suggested_amount is not null:** Confirmed by
  `test_TC4_8_json_contract_fields` (spec T1.7) — the `reason` key must not appear in
  the dict when a valid amount is returned.
- [ ] **Intermediate /tmp file in T3.1 replaced:** The golden set generation step
  (spec T3.1 step 2) writes to `/tmp/golden_raw.json`. On shared systems this is
  world-readable. Replace with a user-local path (e.g., `$(mktemp)` or
  `$HOME/golden_raw.json`) and delete it immediately after the CSV conversion.
- [ ] **Coverage gate:** `src/smart_budget/model.py` must reach ≥ 80% line coverage
  as specified in spec § Mandatory verification. CI must enforce this gate.

---

## Recommendations for the planner

These items should be added to spec.md before handing off to the implementer — they close
gaps found in the threat review.

- **Explicit tenant-isolation contract on `compute_budget_suggestions()`:** Add to the
  function's docstring (and the spec's function signature section): _"Caller guarantees
  that `df` contains data for a single tenant (idclient × idcompany). This function does
  not enforce tenant isolation."_ This makes the security contract explicit before
  DATA-1140 wires the endpoint.

- **statsmodels version bound:** Change `requirements.txt` entry from `statsmodels>=0.14.0`
  to `statsmodels>=0.14.0,<0.15.0` in the spec's T0.1 task description.

- **Golden set SHA-256 provenance:** Add to T3.1: _"Before running the generation script,
  compute `sha256sum data/dough/test/query/smart_budget_synthetic.csv` and include the
  hash in the commit message to prove the golden set was generated from synthetic data."_

- **Intermediate file path for golden set generation:** Replace `/tmp/golden_raw.json`
  in T3.1 step 2 with `$(mktemp)` (bash) or `tempfile.mkstemp()` (Python), and add a
  cleanup step after conversion.

- **Tenant isolation note for DATA-1140:** Add a cross-ticket note: _"When DATA-1140
  activates the endpoint, the API layer must (a) validate the authenticated member's
  session owns every `idaccount` in the request scope, and (b) pass only that member's
  pre-filtered DataFrame to `compute_budget_suggestions()`. model.py does not re-filter."_

---

## Compliance considerations

### NCUA
- No credit union examination findings arise from this ticket in isolation. Smart Budget
  suggestions are advisory; no member account data is modified. If suggestions are
  persisted and exposed to members via the endpoint (DATA-1140), the accuracy and fairness
  of algorithmic financial advice may be subject to NCUA supervisory interest under the
  member service quality standards. No NCUA action required for this ticket.

### BSA/AML
- No BSA/AML impact. The pipeline processes aggregated monthly spending totals — not
  individual transaction amounts — and produces read-only suggestions. No CTR or SAR
  workflows are touched. No transaction monitoring thresholds are modified.

### PCI DSS
- No PCI DSS scope. No PAN, CVV, track data, or cardholder data flows through this
  pipeline. `idaccount` is an internal account identifier, not a PAN.

### State money transmission
- No money transmission occurs in this ticket. Suggestions are advisory only; no funds
  movement is initiated by this pipeline.

---

## Gate decision

**Overall risk: Medium → proceed to `/blossom-workflow:execute`.**

No additional human gate is required. The mandatory controls listed above must be satisfied
by the implementer as part of normal execution. The planner should update spec.md with the
recommendations above before handing off.

## Approval (filled in by the human reviewer, not the agent)

*(Leave blank — Medium risk does not require a human approval line.
`/blossom-workflow:execute` will proceed without it.)*
