from odoo import fields, models


class LegalAiProvider(models.Model):
    # Configuration of an AI/export backend. The core module never imports
    # anything specific to a given provider statically — dispatch happens
    # by provider_type through services/ai_provider_registry.py, exactly
    # like connectors. AI-Brain is one provider_type among others; a
    # contributor can add a new one (Qdrant, OpenWebUI, filesystem JSONL...)
    # without touching the job-processing pipeline.
    _name = "legal.ai.provider"
    _description = "Legal Knowledge Watch: AI/Export Provider"
    _order = "name"

    name = fields.Char(string="Name", required=True)
    provider_type = fields.Selection(
        selection=[
            ("ai_brain_http", "AI-Brain (HTTP)"),
            ("webhook", "Generic Webhook"),
            ("filesystem", "Filesystem (JSONL export, no network)"),
        ],
        string="Provider Type", required=True, default="webhook",
    )
    base_url = fields.Char(string="Base URL")
    auth_mode = fields.Selection(
        selection=[
            ("none", "None"),
            ("bearer", "Bearer Token"),
            ("header", "Custom Header"),
        ],
        string="Authentication", required=True, default="none",
    )
    auth_header_name = fields.Char(
        string="Header Name", default="Authorization",
        help="Used only when Authentication = Custom Header.",
    )
    secret_parameter_key = fields.Char(
        string="Secret Reference",
        help="Name of the ir.config_parameter holding the token/secret — "
             "never the secret's value itself. Set the real value manually "
             "via Settings > Technical > System Parameters. An environment "
             "variable named LKW_AI_PROVIDER_<ID>_TOKEN is checked first "
             "if set (see services/secrets_service.py).",
    )
    timeout_seconds = fields.Integer(string="Timeout (s)", default=20)
    verify_tls = fields.Boolean(string="Verify TLS", default=True)
    enabled_for_classification = fields.Boolean(
        string="Enabled for Classification", default=False,
    )
    enabled_for_export = fields.Boolean(string="Enabled for Export", default=False)
    configuration_json = fields.Text(
        string="Configuration (JSON)",
        help="Provider-specific overrides (e.g. endpoint path overrides for "
             "ai_brain_http). See docs/ai-providers.md.",
    )
    active = fields.Boolean(string="Active", default=True)

    def action_healthcheck(self):
        self.ensure_one()
        from ..services import ai_provider_registry
        from ..services.ai_provider_base import AIProviderError

        try:
            provider = ai_provider_registry.get_provider(self)
            result = provider.healthcheck()
        except AIProviderError as exc:
            return self._notify("danger", str(exc))
        return self._notify(
            "success",
            self.env._("Healthcheck OK: %(result)s", result=result),
        )

    def _notify(self, notif_type, message):
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": notif_type, "message": message,
                "sticky": notif_type == "danger",
            },
        }
