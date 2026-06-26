# StillWriting × Orion-OS CMO — Symbiosis Assessment

*How the two systems perceive, complement, and could compose into one governed marketing operating system.*

Prepared 2026-06-25. Grounded in both codebases (no speculation about features that aren't there).

---

## TL;DR

**Orion-OS CMO is the brain; StillWriting is the voice and the hands.**

- **Orion-OS CMO** decides *what to say, on which channel, why, this week* — strategy, grounded drafting across 9 channels, and one prioritized, human-gated weekly brief.
- **StillWriting** makes it *sound like the actual person, proves it's consented and human-approved, and ships it safely* — a measured Voice Fingerprint, AI-detector screening, consent/disclosure gates, and official-API multi-platform publishing.

They are not two overlapping tools competing for the same job. They are two **adjacent links in one value chain** that already share a constitution, an architecture, and an ethics. One produces governed *intent and grounded drafts*; the other enforces *voice fidelity, compliance, and publish integrity*. Bolt them together and you have a closed loop: **product URL → strategy → grounded weekly plan → voice-faithful drafts → screened + consented + human-approved → compliantly published → metrics back into next week's strategy.**

---

## 1. What each system is (one line)

| | Orion-OS CMO | StillWriting |
|---|---|---|
| **Role** | Autonomous weekly marketing *operator* (the CMO brain) | Human-supervised ghostwriting *production + compliance* engine |
| **Input** | Product URL | A content brief + the byline owner's writing samples |
| **Core artifact** | One prioritized weekly brief (ranked items, per-channel sections, deltas, approval queue) | A voice-matched, detector-screened, approved, published post |
| **Channels** | SEO, GEO, articles, code, Reddit, X, LinkedIn, influencer, UGC | X, Instagram, LinkedIn, Reddit (+ ELI-12 explainers) |
| **Stack** | Python, MCP server (29 tools / 5 resources), 206 tests | TypeScript pure core (M1–M9), 1142 tests, R5 e2e drill |
| **Stops at** | "It never publishes — publishing is the operator's decision" (every drafter agent) | The published post + its disclosure record |

The seam is exactly where one stops and the other starts. Orion's agents **deliberately stop at the draft**; StillWriting **begins at the brief/draft** and carries it through to a compliant publish. They were built to hand off to each other even though neither was built knowing the other existed.

---

## 2. The core thesis — value-chain complementarity

```
   ORION-OS CMO  (decide + draft, grounded)              STILLWRITING  (re-voice + screen + ship, governed)
   ────────────────────────────────────────             ──────────────────────────────────────────────────
   product URL → strategy_context                        ContentBrief (M3)
        │  brand_voice · icp · competitors ·                  │
        │  positioning · growth_playbook                      ▼
        ▼                                                Voice Fingerprint match (M3, 5 sub-scores)
   9 agent workers → grounded drafts ───────────────►        ▼
        │  (Articles, X/LI/Reddit posts, SEO/GEO fixes)  AI-detector gate (M5, fail-closed)
        ▼                                                     ▼
   weekly-orchestrator → ranked brief + approval queue   Ghostwriter approval (M6) + consent/disclosure (M9)
        │                                                     ▼
        └───────── metrics / deltas ◄─────────────────  Official-API publish (M7) + published_post_metrics
```

**Orion answers "what & why."** **StillWriting answers "in whose exact voice, is it allowed, and how does it ship safely."** Neither fully does the other's job, and each is weakest precisely where the other is strongest (see §4).

---

## 3. The five concrete integration seams (file-grounded)

### Seam 1 — Brief / draft handoff *(the spine)*
Orion's drafter agents return review-ready artifacts and explicitly never publish — `agent_writer` returns `Article[]` "for human review… publishing is the operator's decision through the operator"; the `x` / `linkedin` / `reddit` agents draft channel posts the same way. StillWriting's M3 consumes a `ContentBrief` and produces a `Draft`.
**→ Orion's per-channel brief sections and agent drafts map directly onto StillWriting `ContentBrief`s** (pillars, topics, platform targets, audience, constraints). Orion picks the topic and angle with grounded evidence; StillWriting turns it into a publishable post.

### Seam 2 — Voice: strategic intent ↔ measured fidelity *(the sharpest synergy)*
Orion's `StrategyContext.brand_voice` is a **synthesized** descriptor (`brand_voice.tone`, explicitly "not a sourced claim") — a prompt-conditioning hint. StillWriting's **Voice Fingerprint** is a **measured, deterministic, versioned** style signature derived from the person's real samples (consent-gated), enforced by a 5-sub-score voice-match loop.
**→ Orion has the *intent* of voice; StillWriting has the *empirical fidelity* of voice.** Orion's `brand_voice` can seed/condition the brief; StillWriting provides the production-grade voice enforcement Orion structurally lacks. This is the single most valuable complementarity: "on-brand" (Orion) becomes "in this exact human's measured, detector-passing voice" (StillWriting).

### Seam 3 — Publishing: Orion delegates to StillWriting's deeper engine
Both have a gated, content-hash-idempotent publish path, and they share the *same gate philosophy* (approval-first; the transport is never touched without a token). But Orion's `social_publish` is, in its own words, a **"primitive"** for X/LinkedIn. StillWriting's M7 is a full publishing-integrity engine: per-platform **publish-mode resolver** (account-type-aware — IG personal → draft-and-remind, Reddit opt-in, LinkedIn fallback), **official-API-only** discipline, OAuth **token vault**, M9 **disclosure decisions**, **exactly-once**, and an e2e composition proof.
**→ In an integrated system Orion should delegate publishing to StillWriting** rather than use its own primitive. They compose cleanly because both are approval-first + idempotent by construction.

### Seam 4 — Layered human gates (they stack, they don't collide)
Orion: a **strategic** gate — "ship this brief item this week?" (the weekly approval queue). StillWriting: **production** gates — M6 ghostwriter sign-off ("this draft is genuinely in-voice"), M5 detector screen, M9 consent + disclosure.
**→ One coherent escalation:** strategy approval (Orion) → voice/quality/compliance approval (StillWriting) → publish. Two stages of human-in-the-loop, each catching what the other can't see.

### Seam 5 — The metrics feedback loop (closes the circle)
StillWriting's M7 emits `published_post_metrics`. Orion computes **week-over-week deltas from persisted history** and ingests metrics via `fetch_analytics` / `workspace_append_metric`.
**→ StillWriting's post-publish metrics become Orion's next-week signal.** The loop closes: what shipped and how it performed re-conditions next week's strategy. This is what turns the pair from "a pipeline" into "an operating system."

---

## 4. Why integration is low-friction: shared DNA

This is not two random tools — **they are siblings from the same constitution.** StillWriting's Architectural Decision #1 is literally *"Adopt Orion-OS v2.4.9 as base."* Orion-OS CMO **is** "Orion-OS · CMO Edition." They independently exhibit the same engineering genome:

| Trait | Orion-OS CMO | StillWriting |
|---|---|---|
| Governance | `.agents/` constitution + manifest + append-only history | `.agents/` constitution + `manifest.yml` append-only DAG |
| Memory | `memory_bank/` (MASTER_CONTEXT, ARCHITECTURAL_DECISIONS, ALIGNMENT_LOG, active/) | identical structure |
| Decisions | 8 ADRs | 48 ADRs |
| Architecture | adapters over an **injectable Transport** (agents never see a key) | **ports & adapters** (pure core never imports I/O) |
| Ethos | grounded/provenance, glass-box, human-gated, first-party data | glass-box, process-guarantee, human-in-the-loop, consent-owned |
| Safety as code | approval-first publish, PR≠merge, cost caps, whole-word grounding | deny-by-default tenancy, fail-closed gates, official-APIs-only, no "humanizer" |
| Publish discipline | gated + content-hash idempotent | gated + exactly-once + disclosure-recorded |
| Test culture | 206 tests, stdlib-only, audited | 1142 tests, Tier-1 + property-based, two audit rounds |
| Docs | PTD.md, CHANGELOG.md, CONTRIBUTING.md | PTD.md, CHANGELOG.md, CONTRIBUTING.md |

Same governance, same audit discipline, same gate philosophy, even the same idioms (`Result`/`Err` ↔ discriminated unions; frozen dataclasses ↔ `readonly` types; determinism; mocked I/O at the boundary). **Integration won't fight two cultures — it's one culture in two languages.**

---

## 5. Honest friction points (decisions you'll need to make)

1. **Two publish paths.** Recommendation: keep StillWriting's M7 as the *single* publish authority; demote Orion's `social_publish` to "draft handoff" (it already refuses to publish without a token, so this is natural). Don't run both live or you'll double-post across two idempotency stores.
2. **Two notions of "voice."** Orion's `brand_voice` (strategic, synthesized) and StillWriting's Voice Fingerprint (measured, per-person) must be explicitly related: brand_voice conditions the brief; the Fingerprint governs the draft. Decide whose voice ships when they disagree (StillWriting's, by design — it's the measured one with the human gate).
3. **Language boundary.** Orion is Python; StillWriting is TypeScript. The clean contract is **MCP** (Orion already speaks it). StillWriting would expose an MCP server over its existing ports (M3 generate, M5 screen, M6 approve, M7 publish) — a modest, well-bounded build, not a rewrite.
4. **Channel set mismatch.** Overlap on X/LinkedIn/Reddit; Orion adds SEO/GEO/articles/influencer/UGC/code; StillWriting adds Instagram + ELI-12. Map channel-by-channel; not every Orion output routes through StillWriting (an SEO meta-tag fix or a GitHub PR doesn't need a Voice Fingerprint).
5. **Consent scope.** StillWriting will refuse to generate in a person's voice without verified consent (M9). Orion's strategy doesn't model that today — the integration must carry a `subject` + consent reference from brief to draft, or StillWriting hard-fails (correctly).
6. **Two approval queues.** Unify the UX or users will approve twice in two places. The cleanest model: Orion's weekly brief is the single pane; StillWriting's gates surface *inside* a brief item's lifecycle as sub-states.

---

## 6. Recommended integration architecture

**MCP is the contract.** Orion is already a 29-tool MCP server; make StillWriting an MCP server too, and let Orion's `weekly-orchestrator` call it as the production/publish backend.

```
Orion weekly-orchestrator
   │  for each approved brief item that needs a voiced, published post:
   ▼
StillWriting MCP tools (new, thin façades over existing ports):
   sw_generate_in_voice(brief, fingerprintRef)  → Draft        (M3)
   sw_screen(draftId)                            → gateClearedAt (M5)
   sw_request_approval(draftId, ghostwriter)     → ApprovalRecord (M6)
   sw_publish(scheduledPost)                     → PublishedPost + disclosure (M7 + M9)
   sw_metrics(publishedPostId)                   → metrics  ──┐
   ▲                                                          │
   └──────────────── deltas feed next week ◄──────────────────┘ (Orion workspace_append_metric)
```

- **No rewrite either side.** Orion gains a publish/voice backend; StillWriting gains a demand source and a strategy brain. Each keeps its own tests, audits, and manifest.
- The handoff object is a **shared "brief contract"**: Orion's brief item → StillWriting `ContentBrief` (+ a `subject`/consent ref). One adapter, one schema.

---

## 7. Phased path (crawl / walk / run)

- **Crawl (proof of seam):** a one-direction adapter — export an Orion brief item to a StillWriting `ContentBrief` JSON; manually run it through StillWriting; observe a voiced, screened draft. No live publish. Validates Seam 1 + 2.
- **Walk (MCP integration):** StillWriting exposes the four MCP tools above; Orion's orchestrator calls `sw_generate_in_voice` → `sw_screen` → returns drafts into the weekly brief's approval queue. Human approves once, in Orion. Publishing still manual. Validates Seams 3–4.
- **Run (closed loop):** `sw_publish` goes live (official APIs, consent-gated); `sw_metrics` flows back into Orion's deltas. The weekly brief now reports *what actually shipped and how it did.* Validates Seam 5 — the loop is closed.

---

## 8. The combined positioning

Separately: Orion is "the open-source self-hosted AI CMO"; StillWriting is "human-supervised, compliance-grade ghostwriting." **Together they are the first governed, end-to-end marketing operating system that goes from product URL to a published, in-the-founder's-actual-voice, AI-detector-screened, consent-and-disclosure-compliant post — with provenance on every fact and a human gate at every irreversible step.** No SaaS "AI marketer" in either codebase's competitor table does the *whole* chain with this level of auditability and voice fidelity, because none of them pair a strategy brain with a measured-voice + compliance production engine. That whole-chain governance is the moat the pair creates that neither has alone.

---

## 9. Evolution (this round): codebase evidence + a bidirectional advisory + the placement map

Three refinements sharpen the model from a linear pipeline into a **bidirectional, self-grounding loop**.

### 9.1 Evidence = URL **and** codebase (both first-class)
Orion's entry was "give it a URL." Because it's now MCP/adapter-based, the *evidence source* is swappable and **additive** — a codebase is the highest-provenance, lowest-spin source there is (routes, endpoints, feature flags, deps, ADRs, CHANGELOG, commit velocity). The URL doesn't go away; **both feed one `strategy_context`**, and the real unlock is the **three-way diff**:

| Site says it | Code backs it | Reading | Action |
|---|---|---|---|
| ✅ | ✅ | proven proof-point | ship it loudly |
| ✅ | ❌ | overclaim risk | flag it; StillWriting's claims register refuses to publish it |
| ❌ | ✅ | untapped positioning | "marketing you've already earned in the code" |

That third bucket exists *only* if both sources run together. It also ties to StillWriting's **claims register (M9)**: code-grounded capability facts back every public claim, so the combined system structurally cannot publish a feature the code doesn't have.

### 9.2 StillWriting as a strategic advisor (the return path)
StillWriting isn't only "the hands." Its M2 voice-metric engine is text-in/metrics-out, so feeding it the **competitor corpus Orion already gathers** (`crawl`, `reddit_listen`, `discover_creators`) yields a comparative voice/style landscape (archetypes, readability via M4, AI-content signal via M5) → a **content-positioning gap map** that re-conditions Orion's `positioning`/`growth_playbook`/`brand_voice`. **Guardrail:** comparative/diagnostic, never imitative — measuring public competitor content to find white space is analysis; building a fingerprint to clone a competitor's voice would violate StillWriting's voice-ownership ethic and is out of scope by design.

### 9.3 Placement map — where each piece lives

> **Principle:** a capability lives where its engine already is; the consumer holds only a thin client adapter; MCP is the membrane; **never duplicate logic across the boundary.**

| Capability | Engine home | Consumer-side façade | New spec |
|---|---|---|---|
| Codebase-as-evidence (`analyze_codebase`) | **Orion** (strategy evidence; SW has no strategy concept) | — (Orion-internal, behind Transport) | Orion `adapter-codebase-ingest` |
| Voice generation + screen + publish | **StillWriting** (M3/M5/M6/M7; consent + token vault can't move) | Orion client adapter (supersedes `social-publish`) | SW `mcp-server` · Orion `adapter-stillwriting-bridge` |
| Competitor voice-gap advisory | **StillWriting** (M2/M4/M5 engines) | Orion gathers corpus + calls + folds into strategy | SW `voice-gap-advisory` · Orion `adapter-stillwriting-bridge` |

Only **one** piece is single-homed (codebase → Orion). The other two are "both," but **asymmetric**: engine on the owning side, thin client on the consuming side — never duplicated logic. In practice: a couple of new adapter specs in Orion, and StillWriting gaining its first MCP server (a bounded build over ports it already has).

See [`Roadmap.md`](Roadmap.md) for the four specs, the shared contracts, and the phased implementation order.

---

## 10. One-paragraph verdict

The synergy is real and structural, not cosmetic. These are two halves of one machine built — independently — to the same blueprint: Orion-OS CMO is the *strategist and grounded drafter that refuses to publish*; StillWriting is the *voice-faithful, compliance-enforcing publisher that needs a brief*. They share a constitution, an architecture, and an ethic, so the integration is a contract problem (MCP + a brief schema), not a culture clash or a rewrite. The highest-value first move is the smallest one: wire Orion's brief item into a StillWriting `ContentBrief` and watch a strategy-chosen topic come out the other end in the founder's measured voice, screened and ready. Everything else — shared approval UX, live publish, the metrics feedback loop — follows naturally from that seam.
