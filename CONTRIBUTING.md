# Contributing

Thanks for considering a contribution to `legal_knowledge_watch`. This is
an Odoo 18 Community module; the notes below are what you need to get a
change merged, not a general Odoo tutorial.

## Setup

1. An Odoo 18.0 Community environment with this module's addons path
   pointing at `legal_knowledge_watch/`.
2. `pip install requests feedparser beautifulsoup4` — required
   (`external_dependencies` in the manifest, the module refuses to install
   without them). `PyPDF2` is optional (PDF text extraction in the manual-
   import wizard degrades gracefully without it).
3. No external account is required for local development. A Légifrance/
   PISTE watch needs sandbox credentials (`docs/legifrance-piste.md`) —
   everything else (manual import, RSS, OCA DMS, `webhook`/`filesystem` AI
   providers) works with zero external services.

## Running the tests

```bash
odoo --test-enable --stop-after-init -i legal_knowledge_watch -d <test_db>
```

**The full suite must run offline.** Every test that would otherwise reach
the network mocks `requests` (or the equivalent) at the precise
module-qualified import point — see any `tests/test_*.py` file for the
pattern (`@patch("odoo.addons.legal_knowledge_watch.services.<module>.requests.<verb>")`).
A test that needs a real network call, a real DNS resolution, or a real
external service is not acceptable in this suite — see
`services/url_safety.py`'s module docstring for a concrete example of a
design choice (IP-literal SSRF checking, not DNS-resolution-based) made
specifically to keep this rule intact.

New tests go in `tests/test_*.py` and must be imported from
`tests/__init__.py` (Odoo does not auto-discover test modules).

## Code conventions

- No hidden guesswork against an external API or library: if you're
  implementing something against Légifrance/PISTE, OCA DMS, or any other
  external system, ground it in real, current source (official docs,
  a live/independently-verifiable API catalog, or an actively maintained
  open-source client) and say in a comment/doc what was verified vs. what
  wasn't. See `docs/legifrance-piste.md` for the standard this project
  holds itself to.
- New connectors register via `services/connector_registry.py`; new AI/
  export providers via `services/ai_provider_registry.py`. The core
  models never import a concrete connector/provider class directly.
- OCA DMS stays strictly optional: never add it to the manifest's
  `depends`, never import `dms.*` models at module load time outside
  `services/storage_dms.py`'s own availability check.
- AI/export providers stay agnostic: no provider-specific behavior in
  `legal.ai.job`/`legal.knowledge.document` — only `BaseAIProvider`'s
  interface.
- Fail closed on ambiguous or unsafe state: see the export-policy
  unconditional floor (`docs/ai-providers.md`) and the SSRF/redirect/size
  checks (`docs/security.md`) for the pattern — an error or an
  unrecognized state blocks the action, it never falls through to
  "probably fine."
- Never commit a secret. `services/secrets_service.py` is the only
  sanctioned way to read one (environment variable first, then
  `ir.config_parameter`) — never hardcode a token/key, even a test one
  that looks obviously fake (use `patch.dict(os.environ, ...)` in tests).
- Multi-company: any new model with a `company_id` (direct or related)
  needs a matching `ir.rule` in `security/security.xml` — see
  `docs/security.md` for the P0 gap this project shipped once already and
  had to fix.

## Commit / PR conventions

- One logical change per commit; this repo's history uses `feat:`, `fix:`,
  `chore:`, `docs:` prefixes (see `git log`).
- Update `CHANGELOG.md` (Keep a Changelog format) under a new `[Unreleased]`
  or versioned section for any user-visible change, and bump
  `__manifest__.py`'s `version` for anything beyond a docs-only change.
- If your change touches security-relevant behavior (access control,
  secrets, outbound network calls, deletion), update `docs/security.md` in
  the same PR — don't leave the audit document stale.

## Versioning

`MAJOR.MINOR.PATCH` follows Odoo's `18.0.X.Y.Z` convention: `X` bumps per
phase/feature addition, `Y`/`Z` for smaller fixes on top of a released `X`.
See `CHANGELOG.md` for the phase-by-phase history.
