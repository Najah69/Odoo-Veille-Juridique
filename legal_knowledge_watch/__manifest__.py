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

Phase 0: manual import (file upload or pasted text), no network connector.
Phase 1 (this version): adds an RSS/Atom connector, deterministic relevance
rules and a scheduled fetch cron. No AI, no dependency on OCA DMS. Content
is stored via ir.attachment.
    """,
    "version": "18.0.2.0.0",
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
        "views/legal_source_views.xml",
        "views/legal_tag_views.xml",
        "views/legal_watch_views.xml",
        "views/legal_document_views.xml",
        "views/legal_ingestion_run_views.xml",
        "wizard/legal_manual_import_wizard_views.xml",
        "views/menus.xml",
    ],
    "application": True,
    "installable": True,
}
