from odoo import fields, models


class LegalDocumentEnrichment(models.Model):
    # EN: An AI (or future rule-based) analysis result. Never confused with
    # the document's own source content — always a separate, versioned,
    # append-only record. See legal.knowledge.document's module docstring
    # for the source-of-truth principle this enforces.
    # FR: Un résultat d'analyse IA (ou, à terme, à base de règles). Jamais
    # confondu avec le contenu source du document lui-même — toujours un
    # enregistrement séparé, versionné, en ajout seul. Voir la docstring de
    # module de legal.knowledge.document pour le principe de source de
    # vérité que cela impose.
    _name = "legal.document.enrichment"
    _description = "Legal Knowledge Watch: Document Enrichment"
    _order = "create_date desc"

    document_id = fields.Many2one(
        comodel_name="legal.knowledge.document", string="Document",
        required=True, ondelete="cascade", index=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company", string="Company",
        related="document_id.company_id", readonly=True,
        help="Follows the document's company — used by the multi-company "
             "record rule. output_json can contain excerpts/summaries of "
             "the source document, so this must never be visible outside "
             "the document's own company. Deliberately NOT store=True — "
             "see the matching note on legal.ai.job.company_id (a stored "
             "related field can be lazily flushed by the ORM and disturb "
             "write_date-based staleness checks elsewhere in this module; "
             "kept unstored uniformly rather than only where a check "
             "happens to exist today).",
    )
    kind = fields.Selection(
        selection=[
            ("rule_classification", "Rule Classification"),
            ("ai_classification", "AI Classification"),
            ("summary", "Summary"),
            ("impact", "Business Impact"),
            ("embedding_export", "Embedding Export"),
        ],
        string="Kind", required=True,
    )
    provider_id = fields.Many2one(
        comodel_name="legal.ai.provider", string="Provider", ondelete="set null",
    )
    model_identifier = fields.Char(string="Model Identifier")
    prompt_version = fields.Char(string="Prompt Version")
    input_hash = fields.Char(
        string="Input Hash",
        help="SHA-256 of the normalized text this enrichment was computed "
             "from, for reproducibility checks.",
    )
    output_json = fields.Text(string="Output (JSON)")
    confidence = fields.Float(string="Confidence")
    state = fields.Selection(
        selection=[
            ("success", "Success"),
            ("failed", "Failed"),
            ("needs_review", "Needs Review"),
        ],
        string="State", required=True, default="success",
    )
    error_message = fields.Text(string="Error Message")
