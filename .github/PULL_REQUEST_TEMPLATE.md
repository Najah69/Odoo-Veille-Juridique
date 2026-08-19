**What this changes and why**

**Checklist** (see `CONTRIBUTING.md` for detail on each)
- [ ] `odoo --test-enable --stop-after-init -i legal_knowledge_watch -d <test_db>` passes, and every new/changed test still runs fully offline (no real network call).
- [ ] New tests added in `tests/test_*.py` and imported from `tests/__init__.py`.
- [ ] No secret, token, or real credential committed (including in a test fixture).
- [ ] `CHANGELOG.md` updated for any user-visible change; `__manifest__.py`'s `version` bumped for anything beyond docs-only.
- [ ] If this touches access control, secrets, or outbound network calls: `docs/security.md` updated in this same PR.
- [ ] If this adds a connector or AI/export provider: registered via the existing registry pattern (`services/connector_registry.py` / `services/ai_provider_registry.py`), not hand-wired into the core models.

**Test plan**
