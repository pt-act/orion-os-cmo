# Roadmap — StillWriting × Orion-OS CMO Integration

The implementation plan to wire the two systems into one governed marketing loop, per the
[Symbiosis Assessment](symbiosis-assessment.md). This is the **cross-repo source of truth** for the
shared contracts and the build order. Each repo carries a copy of this file at its root.

> **Scope of this document:** it *plans*. The four specs below are authored under each repo's existing
> conventions at status `planned`. Implementation (adapters, the MCP server, tests) happens in the CLI,
> spec by spec, under the normal gates. Nothing here ships code.

---

## The loop we're building

```
 URL  ┐
      ├─► Orion strategy_context ──► brief items ──► [Brief Contract] ──► StillWriting
 code ┘        ▲                                                              │
              │                                                   generate-in-voice → screen
   voice-gap advisory + what-worked metrics                         → approve → publish (official API)
              │                                                              │
              └──────────────── competitor corpus + post metrics ◄──────────┘
```

Orion grounds strategy in **URL + codebase** (the 3-way diff); StillWriting produces in the measured
voice, screens, gets human sign-off, publishes compliantly, then feeds back **post metrics** and a
**competitor voice-gap advisory** that re-conditions next week's strategy.

---

## The four specs

| # | Repo | Spec id | Home | Status | Purpose |
|---|---|---|---|---|---|
| O1 | orion-os-cmo | `adapter-codebase-ingest` | Orion only | planned | Codebase-as-evidence behind Transport + `analyze_codebase` MCP tool; merges with crawl evidence → 3-way diff |
| O2 | orion-os-cmo | `adapter-stillwriting-bridge` | Orion (client of SW) | planned | Outbound MCP client: export brief → call SW publish/voice tools (supersedes `social-publish` for SW channels) + request voice-gap advisory |
| S1 | StillWriting | `mcp-server` | StillWriting (server) | planned | Expose M3/M5/M6/M7 (+M2 read) as MCP tools over the existing ports; ingest the Brief Contract |
| S2 | StillWriting | `voice-gap-advisory` | StillWriting (engine) | planned | M2/M4/M5 comparative analysis over an external competitor corpus → diagnostic advisory (never imitative) |

**Cross-repo dependency:** O2 depends on S1 (it calls SW's MCP tools) and on S2 (it calls the advisory tool).
S1 and S2 depend only on existing StillWriting units. O1 is independent. So the build order is:
**O1 ∥ S1 ∥ S2 first, then O2 last** (it's the integration capstone — same "build the bridge last" discipline as r5-e2e).

---

## Shared contracts (FREEZE THESE FIRST — Phase 0)

All payloads are JSON over MCP (Orion is Python, StillWriting is TypeScript; the wire format is the
contract). Field names are normative.

### C1 — Brief Contract  *(Orion produces → StillWriting `sw_generate_in_voice` consumes)*
```jsonc
{
  "clientId": "string",            // tenant / org id (maps to StillWriting organizationId)
  "subject": {                     // the byline owner whose voice is used
    "subjectId": "string",
    "consentRef": "string"         // REQUIRED — StillWriting M9 hard-fails generation without verified consent
  },
  "fingerprintRef": "string|null", // existing Voice Fingerprint version; null = use latest for subject
  "pillars":  ["string"],
  "topics":   ["string"],
  "platformTargets": ["x"|"linkedin"|"instagram"|"reddit"],
  "audience": "technical"|"non-technical",
  "constraints": { "maxLen": "number|null", "mustInclude": ["string"], "forbiddenCta": ["string"] },
  "brandVoiceHint": "string|null", // from Orion strategy_context.brand_voice.tone (conditioning, not enforcement)
  "sourceEvidence": [              // Orion provenance — every strategic fact traces to a tool output
    { "claim": "string", "source": "string", "kind": "url"|"codebase"|"search"|"reddit" }
  ],
  "correlationId": "string"        // threads Orion brief item → SW draft → publish → metrics
}
```
**Note:** `subject.consentRef` is mandatory. StillWriting will (correctly) refuse to generate in a
person's voice without verified consent (M9). Orion's strategy must carry it from brief to draft.

### C2 — StillWriting MCP tool surface  *(StillWriting S1 produces → Orion O2 consumes)*
```
sw_generate_in_voice(brief: BriefContract)         -> { draftId, draft, voiceMatchScore, accepted }
sw_screen(draftId)                                 -> { gateClearedAt, detectorReport }       # M5
sw_request_approval(draftId, ghostwriterId, note)  -> { approvalId, status }                  # M6
sw_publish(draftId, platform, scheduledFor, idempotencyKey)
                                                   -> { publishedPostId, url, disclosure }    # M7 + M9
sw_metrics(publishedPostId)                        -> { impressions, engagements, ... }       # M7
sw_voice_gap_analysis(corpus, ownVoiceRef?)        -> VoiceGapReport                          # S2 (see C3)
```
Every tool is gated by StillWriting's existing invariants (consent, fail-closed detector gate, M6
approval before publish, official-APIs-only, exactly-once). The MCP layer adds **no new authority** —
it is a typed façade over the ports.

### C3 — Voice-Gap Advisory  *(StillWriting S2 produces → Orion folds into strategy_context)*
```jsonc
// input
{ "corpus": [ { "competitor": "string", "platform": "string", "text": "string", "sourceRef": "string" } ],
  "ownVoiceRef": "string|null" }          // optional: the client's fingerprint, for a gap vector
// output: VoiceGapReport
{ "archetypeLandscape": [ { "competitor": "string", "archetype": "string", "readingGrade": "number" } ],
  "aiContentSignal":   [ { "competitor": "string", "humanReadScore": "number" } ],
  "whitespaceLanes":   ["string"],         // style positions nobody owns
  "advisory":          ["string"],         // diagnostic recommendations for Orion's growth_playbook
  "scrubbed": true }
```
**Guardrail (enforced in the spec):** comparative/diagnostic only. No third-party Voice Fingerprint is
persisted; output never includes "imitate competitor X." This keeps the voice-ownership ethic intact.

### C4 — Codebase Evidence  *(Orion O1 internal; same shape as crawl evidence)*
```jsonc
{ "facts": [ { "claim": "string", "source": "string" /* file path / endpoint */, "kind": "codebase" } ],
  "diff":  { "site_and_code": ["string"], "site_not_code": ["string"], "code_not_site": ["string"] } }
```
Emitted behind Orion's `Transport` seam (the agent never sees a repo token), merged into
`strategy_store.synthesize` alongside crawl evidence. `code_not_site` is the untapped-positioning list;
`site_not_code` feeds overclaim flags (and StillWriting's claims register).

---

## Phased implementation

### Phase 0 — Freeze contracts (no code)
Ratify C1–C4 above. Author the four specs (this deliverable). Approve them under each repo's convention
(StillWriting: 4-gate DoD + `manifest:lock` green; Orion: producer→validator role split, ADR #8, with a
`verdict.md` on approval).

### Phase 1 — CRAWL (prove each seam in isolation)
- **O1 `adapter-codebase-ingest`** — implement the adapter + `analyze_codebase` tool; emit C4 evidence + the 3-way diff. *Done when:* a repo URL yields source-tagged facts that merge into `strategy_context` and the `code_not_site` lane is non-empty on a real product.
- **S1 `mcp-server`** — stand up the StillWriting MCP server exposing C2 tools over the existing ports; `sw_generate_in_voice` accepts C1. *Done when:* a Brief Contract produces a voiced, gate-screened draft via MCP, consent-gated, no live publish.
- **S2 `voice-gap-advisory`** — implement `sw_voice_gap_analysis` over M2/M4/M5; honor the diagnostic-only guardrail. *Done when:* a competitor corpus yields a VoiceGapReport with whitespace lanes; PBT: no third-party fingerprint persisted, output scrubbed.

### Phase 2 — WALK (one-directional integration)
- **O2 `adapter-stillwriting-bridge`** (part 1) — Orion exports an approved brief item → C1 → `sw_generate_in_voice` → `sw_screen`; drafts return into the weekly brief's approval queue. Human approves once, in Orion. Publishing still manual. *Done when:* an Orion-chosen topic comes back as a voiced, screened draft inside the weekly brief.

### Phase 3 — RUN (close the loop)
- **O2 `adapter-stillwriting-bridge`** (part 2) — `sw_publish` goes live (official APIs, consent-gated); `sw_metrics` + `sw_voice_gap_analysis` flow back into Orion's deltas and `strategy_context`. Demote Orion's `social-publish` to the non-SW channels. *Done when:* the weekly brief reports what actually shipped and how it performed, and the advisory measurably re-conditions next week's strategy.

---

## Conventions each spec follows

- **StillWriting (S1, S2):** `stillwriting-platform-specs/specs/<id>/{spec.md, tasks.md, pbt-properties.md}`; a `manifest.yml` DAG node (`type: integration` for S1) with `produces`/`consumes` closed against §C invariants (`tools/manifest_lint.py` must stay exit 0); Mission Alignment Gate 1 in each `spec.md`; Definition of Done = the four gates recorded in manifest history.
- **Orion (O1, O2):** `.agents/specs/<id>/{planning/requirements.md, spec.md, tasks.md}`; a `manifest.yml` spec entry + append-only `history` event; Quality Gate 1 (design-principle alignment) in each `spec.md`; approval via the producer→validator role split (ADR #8) with a `verdict.md` on approval.

## Risks & open decisions
1. **Single publish authority.** On Phase 3, StillWriting's M7 becomes the only publisher for X/LinkedIn/IG/Reddit; Orion's `social-publish` retires for those channels (keep it for any channel SW doesn't cover). Don't run both live (double-post across two idempotency stores).
2. **Consent provenance.** The Brief Contract's `subject.consentRef` must resolve to a real M9 verified-consent record, or generation hard-fails by design. Orion's strategy model needs a `subject`/consent field it doesn't have today.
3. **Transport for the bridge.** Orion reaches StillWriting via an MCP client transport behind its `Transport` seam — the agent never holds StillWriting credentials; same first-party posture as the rest of Orion.
4. **Two approval UXs.** Unify on Orion's weekly brief as the single pane; surface StillWriting's M5/M6/M9 gates as sub-states of a brief item rather than a second queue.
5. **Versioning the contracts.** C1–C4 are versioned; a breaking change is a manifest history event in both repos.

## Deliverables in each zip
- **orion-os-cmo.zip:** the repo + new `.agents/specs/adapter-codebase-ingest/` and `adapter-stillwriting-bridge/`, manifest entries + history, memory-bank update, this `Roadmap.md`, and the assessment.
- **StillWriting.zip:** the repo + new `stillwriting-platform-specs/specs/mcp-server/` and `voice-gap-advisory/`, manifest DAG entries + history (`manifest:lock` green), memory-bank update, this `Roadmap.md`, and the assessment.
