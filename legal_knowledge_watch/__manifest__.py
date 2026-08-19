# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl-3.0.html)

{
    "name": "Legal Knowledge Watch",
    "summary": "Collect, qualify and archive reliable legal knowledge",
    "description": """
Legal Knowledge Watch
======================
Collects, normalizes, deduplicates and archives legal/regulatory content from
trusted sources, with a human review workflow and a locally-owned document
history.

This module is a documentation and monitoring tool. It does not provide
legal, tax or accounting advice, and does not replace consultation with a
qualified professional.

Phase 0: manual import (file upload or pasted text).
Phase 1: RSS/Atom connector, deterministic relevance rules, scheduled fetch
cron.
Phase 2: optional OCA DMS storage backend, selectable per watch/import
(auto/dms/attachment). OCA DMS is never a hard dependency — the module
installs and works fully with the ir.attachment fallback alone.
Phase 3: Légifrance/PISTE connector (LODA collection — lois, ordonnances,
décrets, arrêtés). See docs/legifrance-piste.md for exactly what was
verified against real sources vs. what still needs checking against a
live PISTE sandbox account.
Phase 4: agnostic AI/export provider layer. The core never imports a
specific provider — AI-Brain (a generic HTTP contract, see
docs/ai-providers.md) is one provider_type among others, alongside a
minimal generic webhook provider. AI never overrides human decisions:
classification results only ever set a "needs review" flag, and export to
any provider only ever happens for approved, current, non-empty,
primary/high-trust documents — enforced by policy, not by convention.
Phase 5: configurable export policies, reconciliation (detects and repairs
drift between local state and any export index — never by deleting local
history), retention (archive, then — well after an explicit grace period —
purge only non-current version binaries; the current version and every
metadata row are always kept), and a network-free filesystem/JSONL export
provider. Odoo remains the durable registry; any export index is a
reconstructible projection of it.
Phase 6: security audit and release-candidate hardening. Closed a
cross-company data-exposure gap on 5 models (missing ir.rule despite
carrying company_id), restricted legal.document.version writes to the
sanctioned creation path only (no more direct-ORM forgery by a plain
User), and added SSRF/redirect/response-size protection to every outbound
call to an admin-configured URL (RSS feed_url, AI provider base_url) plus
redirect protection on the Légifrance/PISTE connector and OAuth token
call. See docs/security.md for the full audit, including what remains a
documented residual risk (hostname-based SSRF via DNS is out of scope —
resolving DNS here would break this project's offline test suite).
Phase 8: OpenFisca connector — watches specific legislative parameters
(e.g. SMIC, plafond de la Sécurité sociale) for a new dated value,
distinct from the document-feed model RSS/Légifrance use. See
docs/openfisca.md for exactly what was verified against the real, public
api.fr.openfisca.org API (no account needed) and cross-checked against
the open-source openfisca-france parameter source files. Scale/bareme
parameters (a structurally different response shape) are explicitly out
of scope for this phase.
Phase 9 (this version): Open Lefebvre Dalloz connector — watches the
free legal-news portal's /actualites listing. No documented public
API/RSS exists for this site (checked live); the connector instead
parses the __NEXT_DATA__ JSON every Next.js page embeds in its raw
server-rendered HTML — real structured data, but an internal
implementation detail rather than a stable public contract, unlike
Légifrance/OpenFisca. See docs/open-lefebvre-dalloz.md for the full
grounding and residual-risk disclosure.
    """,
    "version": "18.0.9.0.0",
    "category": "Tools",
    "author": "Chapeau Blanc Group, Community Contributors",
    "website": "https://github.com/Najah69/Odoo-Veille-Juridique",
    "license": "AGPL-3",
    "depends": [
        "base",
        "mail",
    ],
    "external_dependencies": {
        "python": ["requests", "feedparser", "bs4"],
    },
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "data/legal_sequence.xml",
        "data/legal_tags.xml",
        "data/ir_cron.xml",
        "data/legifrance_config_parameters.xml",
        "views/legal_source_views.xml",
        "views/legal_tag_views.xml",
        "views/legal_watch_views.xml",
        "views/legal_document_views.xml",
        "views/legal_ingestion_run_views.xml",
        "views/legal_dms_directory_route_views.xml",
        "views/legal_ai_provider_views.xml",
        "views/legal_ai_job_views.xml",
        "views/legal_export_policy_views.xml",
        "views/legal_retention_policy_views.xml",
        "wizard/legal_manual_import_wizard_views.xml",
        "views/menus.xml",
    ],
    "application": True,
    "installable": True,
}
