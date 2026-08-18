from odoo import fields, models


class LegalDocumentEnrichment(models.Model):
    # An AI (or future rule-based) analysis result. Never confused with the
    # document's own source content — always a separate, versioned,
    # append-only record. See legal.knowledge.document's module docstring
    # for the source-of-truth principle this enforces.
    _name = "legal.document.enrichment"
    _description = "Legal Knowledge Watch: Document Enrichment"
    _order = "create_date desc"

    document_id = fields.Many2one(
        comodel_name="legal.knowledge.document", string="Document",
        required=True, ondelete="cascade", index=True,
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
