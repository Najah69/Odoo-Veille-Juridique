from odoo import fields, models


class LegalRetentionWizard(models.TransientModel):
    # Deliberately separate from the (disabled-by-default, dry-run-only)
    # cron: this is how an administrator actually applies retention for
    # real, one conscious click at a time. See
    # legal.knowledge.document._cron_apply_retention() and
    # docs/operations.md.
    _name = "legal.retention.wizard"
    _description = "Legal Knowledge Watch: Apply Retention"

    dry_run = fields.Boolean(
        string="Dry Run", default=True,
        help="When set, nothing is written — only a report of what would "
             "happen.",
    )

    def action_apply(self):
        self.ensure_one()
        report = self.env["legal.knowledge.document"]._cron_apply_retention(
            dry_run=self.dry_run, batch_size=500,
        )
        message = self.env._(
            "%(mode)s: %(archived)s document(s) archived, %(purged)s "
            "old-version binary(ies) purged.",
            mode=self.env._("Dry run") if self.dry_run else self.env._("Applied"),
            archived=len(report["archived"]), purged=len(report["purged_versions"]),
        )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {"type": "info", "message": message, "sticky": True},
        }
