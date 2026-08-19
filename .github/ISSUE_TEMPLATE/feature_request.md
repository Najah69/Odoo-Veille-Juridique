---
name: Feature request
about: Propose a new connector, provider, or capability
labels: enhancement
---

**What problem does this solve, and for whom**

**Proposed approach**
If this is a new connector or AI/export provider, note whether it can
follow the existing `BaseConnector`/`BaseAIProvider` registry pattern
(see `docs/connectors.md` / `docs/ai-providers.md`) — most new
integrations should.

**Grounding**
If this involves an external API or library, what real, current source
would you ground the implementation in (official docs, a live/
independently-verifiable API catalog, an actively maintained open-source
client)? See `docs/legifrance-piste.md` for the standard this project
holds itself to — no hand-waved API assumptions.

**Alternatives considered**
