"""Simple, non-technical reading page for legal.knowledge.document —
what a non-technical stakeholder (e.g. the "Veille juridique" dashboard
button) should land on, as opposed to the Watches configuration screen.

FR : Page de lecture simple et non technique pour legal.knowledge.document
— ce sur quoi un utilisateur non technicien (ex : le bouton dashboard
« Veille juridique ») doit atterrir, par opposition à l'écran de
configuration des veilles.
"""
from odoo import http
from odoo.http import request

DEFAULT_LIMIT = 50
PREVIEW_LENGTH = 600

# EN: One badge color per status, matching this project's existing
# "one accent, restrained default styling" diagram convention rather
# than a fresh color scheme.
# FR : Une couleur de badge par statut, reprenant la convention déjà
# établie dans ce projet (« un seul accent, style par défaut sobre »)
# plutôt qu'une nouvelle palette.
_STATUS_BADGE_CLASS = {
    "new": "bg-secondary",
    "qualified": "bg-info text-dark",
    "review": "bg-warning text-dark",
    "approved": "bg-success",
    "rejected": "bg-danger",
    "archived": "bg-dark",
    "superseded": "bg-secondary",
}


class LegalWatchReaderController(http.Controller):

    @http.route("/veille-juridique", type="http", auth="user", website=True)
    def reader(self, **kw):
        # EN: No sudo() — this page respects the visiting user's own
        # legal_knowledge_watch group/company access exactly like the
        # backend would, it is a friendlier view of the same data, not
        # a bypass of it.
        # FR : Pas de sudo() — cette page respecte l'accès
        # groupe/société propre à l'utilisateur qui la consulte,
        # exactement comme le backend le ferait ; c'est une vue plus
        # accueillante des mêmes données, pas un contournement.
        documents = request.env["legal.knowledge.document"].search(
            [], order="collected_at desc", limit=DEFAULT_LIMIT,
        )
        rows = [
            (doc, _STATUS_BADGE_CLASS.get(doc.status, "bg-secondary"))
            for doc in documents
        ]
        # EN: Resolved by xml_id, never hardcoded — the numeric action id
        # is database-specific (e.g. 944 on chapeau_blanc_group is not
        # portable to any other install of this module).
        # FR : Résolu par xml_id, jamais codé en dur — l'id numérique
        # d'action est propre à chaque base (ex. 944 sur
        # chapeau_blanc_group n'est pas portable vers une autre
        # installation de ce module).
        settings_action = request.env.ref(
            "legal_knowledge_watch.action_legal_watch", raise_if_not_found=False,
        )
        return request.render(
            "legal_knowledge_watch.legal_watch_reader_page",
            {
                "rows": rows,
                "preview_length": PREVIEW_LENGTH,
                "settings_action_id": settings_action.id if settings_action else None,
            },
        )
