# Orion-OS · CMO Edition

An autonomous **marketing operator**. Give it a product URL; it reads the product
into a strategy, runs a team of agent workers that draft review-ready work across SEO, GEO,
content, social, code, and creator outreach, and converges everything into one prioritized
**weekly brief** with week-over-week deltas and a human-gated approval queue.

**Client-agnostic MCP server** — capabilities ship as standard MCP tools (29 tools, 5 resources)
consumable by any MCP-compatible client (Claude Code, Cursor, Desktop app, custom).

Two principles make it different from a black-box "AI marketer":

- **Grounded & auditable.** Every metric, score, ranking, or competitor fact in a draft
  traces to a tool output. The model reasons and writes; it never invents numbers.
- **Human-gated & first-party.** Nothing is published, posted, or merged without an explicit
  approval token. Product data stays on your infrastructure; the data path is self-hosted.

> **Status:** build-complete — **206 tests green, 29 MCP tools, 5 resources, CI/CD live**.
> Client-agnostic LLM support shipped (any OpenAI-compatible provider via env vars).
> Self-verified single-model build under an independent producer → validator role split (ADR #8).

> **Positioning:** The only open-source, self-hosted AI CMO with provenance-grounded agents and first-party data sovereignty.

## How it compares

The "AI CMO" category is emerging. Here's how Orion-OS stacks up:

| Category | Player | Their model | Orion-OS differentiator |
|---|---|---|---|
| **AI CMO (SaaS)** | Okara ($99/mo, 6 agents) | Proprietary cloud, opaque scores, auto-publishes | Open-source, self-hosted, every metric traces to a tool call, human-gated publish |
| **Multi-agent AI marketing** | NoimosAI ($99–499/mo) | Proprietary cloud agents for SMBs | First-party data — strategy never leaves your infra |
| **OS marketing automation** | Mautic (250K+ installs) | PHP email/campaign builder, no AI agents | AI-native: 9 strategy-conditioned agent workers over MCP |
| **Agent frameworks** | CrewAI (45K★), AutoGen, LangGraph | SDK to define agent roles and crews | Pre-built product: agents, strategy store, orchestrator, production workspace |
| **AI writing platforms** | Jasper ($39–69/mo), Copy.ai ($24–49) | Human-in-loop writing with templates | Autonomous weekly operator across 9 channels converging to one brief |
| **General AI agents** | AutoGPT (170K★) | No marketing specialization | Purpose-built for weekly marketing ops with provenance enforcement and human gates |

---

## How it works

```
product URL
   │
   ▼
strategy-store ──► strategy_context  { brand_voice, icp, competitors, positioning, playbook }
   │                     (versioned, hand-editable; every agent conditions on it)
   ▼
9 agent workers ──► drafts            seo · geo · writer · coding · reddit · x · linkedin · influencer · ugc
   │  (each draft's facts trace to a tool output; provenance enforced in code)
   ▼
weekly-orchestrator ──► one prioritized brief  { ranked items, per-agent sections, deltas, approval queue }
   │
   ▼
MCP Server ──► 29 tools + 5 resources exposed over stdio MCP (any client)
```

- **`strategy-store`** turns crawled, source-tagged evidence into a five-section
  `strategy_context`. Ungrounded claims are dropped; operator edits survive refresh.
- **Adapters** are typed tool façades (self-describing, structured output, atomic/idempotent)
  over an **injectable `Transport`** — so the agents never see a key and the backend is
  swappable. Read-only/analysis adapters (analytics, SEO audit, GEO probe, Reddit listen,
  creator discovery) and gated side-effect adapters (GitHub PR, social/CMS publish, video).
- **Agent workers** are strategy-conditioned drafters. Each enforces a provenance gate in
  code (e.g. a fabricated `issue_id`/`finding_id`/`gap_ref`/keyword is dropped, never
  shipped). Their system prompts compose from one shared directive spine
  (`llm/principles.py`).
- **`weekly-orchestrator`** fans out to the enabled agents (a failure is captured, not fatal),
  computes deltas from persisted history only, and assembles a deterministic brief behind a
  publish gate that refuses any irreversible action without a recorded approval.
- **`mcp-server`** exposes every adapter and workspace operation as standard MCP tools/resources.
  Start with `uv run python -m orion_os_cmo.mcp_server.server`. Any MCP client connects.

### Safety gates (enforced in code, not just prompts)
- **Approval-first publish.** Social/CMS publish refuse with no valid token — the transport
  is never touched. Posting is content-hash idempotent.
- **PR ≠ merge.** The GitHub adapter exposes only `open_pr`; there is structurally no merge
  path.
- **Cost cap.** Video generation quotes first and renders only within the per-run cap.
- **Grounding.** GEO "mentioned" is a whole-word match against the literal answer text;
  creator `audience_fit` is grounded or `null`, never fabricated.

---

## MCP Server

The MCP server exposes all adapters and workspace operations as standard MCP tools.

```bash
uv run python -m orion_os_cmo.mcp_server.server
# Connects over stdio. Add to your MCP client config:
# {
#   "mcpServers": {
#     "orion-cmo": {
#       "command": "uv",
#       "args": ["run", "python", "-m", "orion_os_cmo.mcp_server.server"]
#     }
#   }
# }
```

Configure via environment:

```bash
export CMO_WORKSPACE_ROOT=".agents/memory_bank-production/"  # workspace path
export ORION_SEARCH_PROVIDER=brave                           # search provider
export ORION_SEARCH_API_KEY=...                              # search API key
export CMO_VIDEO_CAP=50                                      # video cost cap (USD)
export LLM_API_URL=https://api.openai.com/v1                 # LLM provider base URL
export LLM_API_KEY=...                                       # LLM API key
export LLM_MODEL=gpt-4o                                      # model name
```

**29 tools:**

| Group | Tools |
|-------|-------|
| **A** Data-collection | `seo_audit`, `fetch_analytics`, `geo_probe`, `crawl_page`, `reddit_search`, `discover_creators` |
| **B** Side-effect | `open_pr`, `quote_video`, `render_video` |
| **C** Workspace mgmt | `workspace_init`, `workspace_read_strategy`, `workspace_write_strategy`, `workspace_create_output`, `workspace_advance_output`, `workspace_read_metrics`, `workspace_append_metric`, `workspace_read_outputs`, `workspace_read_approvals`, `workspace_read_runs` |
| **E** Agent-run | `agent_run_seo`, `agent_run_geo`, `agent_run_reddit`, `agent_run_x`, `agent_run_linkedin`, `agent_run_writer`, `agent_run_coding`, `agent_run_influencer`, `agent_run_ugc` |
| **F** Orchestrator | `orchestrator_run` |

**5 resources:** `workspace://strategy`, `://metrics`, `://outputs`, `://approvals`, `://runs`

---

## The data layer is self-hosted (ADR #7)

External data runs on **your** infrastructure behind the `Transport` seam — no paid
aggregator in the path, no query egress to a third party. External spend reduces to model
tokens.

| Capability | Backend |
|---|---|
| Page read (`scrape`) | headless browser (Playwright) |
| SEO audit (`lighthouse`) | local Lighthouse subprocess (`npx lighthouse`) |
| On-page analysis | stdlib HTML parse (no third party) |
| Web search (`search`) | **your own key** to Brave / Bing / SerpAPI (optional) |

Configure via environment (read behind the boundary; never passed to an agent):

```bash
export ORION_SEARCH_PROVIDER=brave          # brave | bing | serpapi   (optional — for web search)
export ORION_SEARCH_API_KEY=…               # your own key (stays inside the transport)
export ORION_LIGHTHOUSE_CMD="npx lighthouse {url} --output=json --quiet --chrome-flags=--headless"
export ORION_HEADLESS=1
```

---

## Install & run

The harness is a plain Python package. The bundled runtime is **`uv`** (no global Python
install needed). The test suite is stdlib-only, so it runs with **zero third-party installs**.

```bash
# run the full test suite (206 tests)
uv run python -m unittest            # or: python3 -m unittest discover -s tests

# boot the MCP server
uv run python -m orion_os_cmo.mcp_server.server

# boot the self-hosted data transport and inject it into the adapters
#   see examples/self_hosted_harness_boot.py
```

Requirements for a **live** run (not for tests): a Chromium-capable Playwright install
(scrape), Node + Lighthouse (audit), and — if you want web-search evidence — a search-API
key. None are needed to run the suite (the external actions are injectable and mocked).

---

## Layout

```
orion_os_cmo/
  strategy_store/      strategy_context: retrieval, grounded synthesis, versioned persistence
  client_workspace/    durable per-client store: append-only metrics, publish gate, write-once runs
  adapters/            10 typed tool façades over an injectable Transport
  agent_{seo,geo,coding,writer,reddit,x,linkedin,influencer,ugc}/   strategy-conditioned drafters
  orchestrator/        weekly fan-out, deltas, deterministic brief, publish gate
  transports/          SelfHostedTransport (Playwright / Lighthouse / own-key search / on-page)
  mcp_server/          FastMCP stdio server (29 tools, 5 resources, client-agnostic)
  llm/                 LLMClient protocol + HttpLLMClient + principles.py (shared agent directives)
.agents/
  AGENTS.project.md    the CMO constitution (deviations + never-do rules)
  manifest.yml         the spec index + append-only history (the audit trail)
  specs/<id>/          per-capability 3-phase spec (planning → spec → tasks) + verdicts
  memory_bank/         MASTER_CONTEXT, ARCHITECTURAL_DECISIONS, ALIGNMENT_LOG, active/
docs/
  index.html           client-agnostic documentation site
  CODE_QUALITY_AUDIT.md independent code-quality audit (all 12 findings closed)
CHANGELOG.md
CONTRIBUTING.md
LICENSE                MIT
```

---

## Status

- **206 / 206 tests green**, modules import clean.
- **MCP server:** 29 tools (Groups A–F), 5 resources, client-agnostic (any MCP client).
- **`manifest.status: complete`**, independently signed off 2026-06-20.
- **All 12 CODE_QUALITY_AUDIT findings closed** (2026-06-25).
- **§4 carve-outs closed** — `RankedFix.rationale` field, agent-x thread-format validation.
- **Client-agnostic LLM support shipped** — `HttpLLMClient` works with any OpenAI-compatible provider via `LLM_API_URL` / `LLM_API_KEY` / `LLM_MODEL` env vars. CI/CD pipeline and CONTRIBUTING.md in place. The concrete Claude client is deferred; bring your own provider.

See `CHANGELOG.md` for the release history and `.agents/specs/<id>/verdict.md` for the
validation records.
