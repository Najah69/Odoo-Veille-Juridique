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
Phase 3 (this version): Légifrance/PISTE connector (LODA collection —
lois, ordonnances, décrets, arrêtés). See docs/legifrance-piste.md for
exactly what was verified against real sources vs. what still needs
checking against a live PISTE sandbox account. No AI yet.
    """,
    "version": "18.0.4.0.0",
    "category": "Tools",
    "author": "Chapeau Blanc Group, Community Contributors",
    "website": "https://github.com/Najah69/odoo-legal-knowledge-watch",
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
        "wizard/legal_manual_import_wizard_views.xml",
        "views/menus.xml",
    ],
    "application": True,
    "installable": True,
}
