# Orion-OS · CMO Edition — Product Technical Document

> **Version:** 0.6.0 (pre-release)
> **Date:** 2026-06-25
> **Status:** Complete — 29 MCP tools, 206 tests green, CI/CD live
> **Stack:** Python 3.11+ · uv · fastmcp (MCP transport)

---

## 1. Product Overview

Orion-OS · CMO Edition is a weekly autonomous marketing operator — a strategy-driven system
that takes a product URL, builds a grounded brand strategy, runs a team of agent workers
across SEO, GEO, content, social, code, and creator outreach, and produces a single
prioritized weekly brief with week-over-week deltas and a human-gated approval queue.

### 1.1 Core Principles

- **Grounded & auditable.** Every factual claim traces to a tool output. No invented
  metrics, competitors, or positioning.
- **Human-gated & first-party.** Nothing publishes without an explicit approval token.
  Product data stays on your infrastructure.
- **Client-agnostic MCP.** All capabilities are standard MCP tools. Any MCP
  client — Claude Code, Desktop, Cursor, custom — can connect.
- **Self-hosted data.** The data-acquisition path runs on operator-owned backends
  behind an injectable `Transport` seam. External spend reduces to model tokens.

### 1.2 Architecture Diagram

```
                         ┌──────────────────────┐
                         │    MCP Client (any)   │
                         │ Claude Code · Desktop │
                         │ Cursor · Custom       │
                         └────┬───┬──────────────┘
                              │   │  stdio MCP
                    ┌─────────▼───▼──────────────┐
                    │  mcp-server (fastmcp)       │
                    │  19 tools · 5 resources     │
                    └────┬───┬───┬───┬────────────┘
                         │   │   │   │
              ┌──────────┘   │   │   └──────────┐
              ▼              ▼   ▼               ▼
     ┌────────────┐   ┌───────────┐   ┌──────────────────┐
     │ Adapters   │   │ Workspace │   │ Orchestrator     │
     │ (10 tools) │   │ Store     │   │ (weekly loop)    │
     └──────┬─────┘   └───────────┘   └──────────────────┘
            │  injectable Transport
     ┌──────▼──────┐
     │ Transports  │
     │ Self-hosted │
     └─────────────┘
```

---

## 2. System Components

### 2.1 MCP Server (`orion_os_cmo/mcp_server/`)

FastMCP stdio server exposing all system capabilities as MCP tools and resources.
**server.py (199 lines) + tools_ef.py (166 lines), 29 tools, 5 resources.** Client-agnostic — zero Claude-specific code.

**Tool groups:**

| Group | Count | Tools | Description |
|-------|-------|-------|-------------|
| A — Data-collection | 6 | `seo_audit`, `fetch_analytics`, `geo_probe`, `crawl_page`, `reddit_search`, `discover_creators` | Read-only adapter wrappers |
| B — Side-effect | 3 | `open_pr`, `quote_video`, `render_video` | Gated action tools |
| C — Workspace | 10 | `workspace_init`, `workspace_read_strategy`, `workspace_write_strategy`, `workspace_create_output`, `workspace_advance_output`, `workspace_read_metrics`, `workspace_append_metric`, `workspace_read_outputs`, `workspace_read_approvals`, `workspace_read_runs` | Workspace CRUD tools |
| E — Agent-run | 9 | `agent_run_seo`, `agent_run_geo`, `agent_run_reddit`, `agent_run_x`, `agent_run_linkedin`, `agent_run_writer`, `agent_run_coding`, `agent_run_influencer`, `agent_run_ugc` | Per-agent run tools (client-agnostic `HttpLLMClient`) |
| F — Orchestrator | 1 | `orchestrator_run` | Full weekly pass tool |

**29 tools total** across all groups.

**Resources:**

| URI | Returns | Description |
|-----|---------|-------------|
| `workspace://strategy` | `dict` | Current strategy context |
| `workspace://metrics` | `list[MetricRow]` | Append-only metric time-series |
| `workspace://outputs` | `list[OutputRow]` | Drafted/approved/published outputs |
| `workspace://approvals` | `list[ApprovalEntry]` | Human decision audit trail |
| `workspace://runs` | `RunRecord` | Last weekly run record |

**Transport config** (environment variables):
- `CMO_WORKSPACE_ROOT` — workspace path (default: `.agents/memory_bank-production/`)
- `ORION_SEARCH_PROVIDER` — search backend (`brave`/`bing`/`serpapi`)
- `ORION_SEARCH_API_KEY` — search API key
- `CMO_VIDEO_CAP` — video cost cap in USD (default: 50)
- `LLM_API_URL` — LLM provider base URL (default: `https://api.openai.com/v1`)
- `LLM_API_KEY` — LLM API key
- `LLM_MODEL` — model name (default: `gpt-4o`)
- `LLM_MAX_TOKENS` — max tokens (default: `4096`)

### 2.2 Adapters (`orion_os_cmo/adapters/`)

10 typed tool façades over an injectable `Transport` protocol. All I/O and secrets
behind the boundary. Structured `Ok`/`Err` results throughout.

| Adapter | Method | Returns | Safety |
|---------|--------|---------|--------|
| `analytics_ingest` | `fetch_analytics()` | `AnalyticsSnapshot` | Read-only |
| `seo_audit` | `seo_audit(url)` | `AuditReport` | Read-only |
| `crawl` | `scrape(url)` | `ScrapeResult` | Read-only |
| `geo_probe` | `probe(brand, questions, models)` | `GeoReport` | Read-only |
| `reddit_listen` | `reddit_search(keywords)` | `RedditSearchResult` | Read-only |
| `creator_discovery` | `discover_creators(niche, platform)` | `list[Creator]` | Read-only |
| `video_gen` | `generate_video(prompt, ...)` | `VideoAsset` | Cost-capped |
| `github_pr` | `open_pr(repo, branch, diff, desc)` | `PRResult` | No merge path |
| `social_publish` | `publish_post(platform, content, token)` | `PublishResult` | Approval-gated |
| `cms_publish` | `publish_article(slug, body, token)` | `PublishResult` | Approval-gated |

All adapters are frozen dataclass contracts with provenance gates enforced in code.

### 2.3 Agent Workers (`orion_os_cmo/agent_*/`)

9 strategy-conditioned drafting agents. Each reads the `strategy_context`, pulls data
through one adapter tool, and produces review-ready drafts. All compose system prompts
from `llm/principles.py` (`SPINE` + `VOICE` + `compose()`).

| Agent | Adapter | Drafts |
|-------|---------|--------|
| `agent_seo` | `seo_audit` | Ranked on-page fixes |
| `agent_geo` | `geo_probe` | GEO visibility fixes |
| `agent_coding` | `github_pr` | Code change → PR |
| `agent_writer` | `cms_publish` | SEO articles + GEO FAQ |
| `agent_reddit` | `reddit_listen` | Thread replies |
| `agent_x` | `social_publish` | Posts + threads |
| `agent_linkedin` | `social_publish` | Founder-voice posts |
| `agent_influencer` | `creator_discovery` | Outreach drafts |
| `agent_ugc` | `video_gen` | Video briefs |

Provenance gates: fabricated `issue_id`, `finding_id`, `gap_ref`, keyword are dropped
in code. Every output claim traces to a tool with verifiable source.

### 2.4 Orchestrator (`orion_os_cmo/orchestrator/`)

Weekly integration layer. Fires all enabled agents, captures failures (never fatal),
computes week-over-week deltas from persisted history, assembles a deterministic brief,
and gates all irreversible actions through `PublishGate`.

| Module | Responsibility |
|--------|---------------|
| `coordinator.py` | Agent registry + dispatch (dict lookup) |
| `agent_runner.py` | Fault-isolated execution |
| `delta_engine.py` | Week-over-week deltas from persisted history |
| `assembler.py` | Deterministic brief construction + markdown renderer |
| `publish_gate.py` | Human-approval gate (no token → no transport touch) |

### 2.5 Strategy Store (`orion_os_cmo/strategy_store/`)

Root artifact builder. Crawls product URL into source-tagged `EvidenceSet`, synthesizes
five-section `StrategyContext` (brand_voice, icp, competitors, positioning, playbook).
Ungrounded claims are dropped in code. Operator edits survive refresh via hash-baseline
versioning.

### 2.6 Client Workspace (`orion_os_cmo/client_workspace/`)

Per-client durable store over `.agents/memory_bank-production/`. Append-only metrics
(with provenance requirements), write-once run records, lifecycle-gated outputs/approvals,
human-readable strategy files.

| Store | Backing file | Capacity |
|-------|-------------|----------|
| Strategy | `client_context.md` + `_meta.json` | Hash-baseline versioned |
| Metrics | `metrics.md` | Append-only, source-required |
| Outputs | `outputs.md` | Lifecycle: drafted → approved → published |
| Approvals | `approvals.md` | Append-only human decision log |
| Runs | `runs/*.md` | Write-once per ISO week |
| Config | `config.yml` | Client config (cadence, agents, accounts) |

### 2.7 Transports (`orion_os_cmo/transports/`)

`SelfHostedTransport` — the operator-owned data path behind the `Transport` seam.
Dispatches adapter paths to local handlers:

| Path | Handler | Implementation |
|------|---------|---------------|
| `firecrawl/scrape` | `_scrape` | Playwright headless browser |
| `exa/search` | `_search` | Own-key HTTP (Brave/Bing/SerpAPI) |
| `lighthouse/run` | `_lighthouse` | `npx lighthouse` subprocess |
| `onpage/analyze` | `_onpage` | stdlib `html.parser` |

Secrets (`ORION_SEARCH_API_KEY`) live only inside `TransportConfig` (excluded from `repr`).

### 2.8 LLM Protocol (`orion_os_cmo/llm/`)

Pluggable `LLMClient` Protocol (`types.py`) + `HttpLLMClient` (`http_client.py`, stdlib-based) +
`LLMConfig` (`config.py`, env-var configured) + shared agent directives (`principles.py`).

```python
class LLMClient(Protocol):
    def complete(self, system: str, prompt: str) -> Result[str, str]: ...
    def complete_json(self, system: str, prompt: str, schema: type[T]) -> Result[T, str]: ...
```

`HttpLLMClient` implements the Protocol against any OpenAI-compatible Chat Completions API.
Configured via env vars: `LLM_API_URL` (default `https://api.openai.com/v1`), `LLM_API_KEY`,
`LLM_MODEL` (default `gpt-4o`), `LLM_MAX_TOKENS` (default `4096`). No Claude-specific code.

The shared `principles.py` spine (`SPINE` + `VOICE` + `compose()`) is wired into all 9 agents.

---

## 3. Data Model

Every typed contract is a frozen dataclass (H-2 structured output). Key types:

### 3.1 Common

```python
class Result = Ok[T] | Err[E]   # Discriminated union
class Ok(Generic[T]):
    value: T
    ok: Literal[True]
class Err(Generic[E]):
    error: E
    ok: Literal[False]
```

### 3.2 Strategy

```python
class StrategyContext:
    brand_voice: dict        # tone, do[], dont[]
    icp: str                 # ideal customer profile
    competitors: list[...]   # name, url, positioning, source
    positioning: dict        # one_liner, differentiators[]{claim, source}
    growth_playbook: str
    _meta: dict              # version, built_at, per-section hashes
```

### 3.3 Workspace

```python
class MetricRow:
    date: str       # YYYY-MM-DD
    metric: str     # metric name
    value: float    # numeric value
    source: str     # provenance (tool call id)

class OutputItem:
    date: str
    agent: str      # which agent produced it
    type: str       # content type
    provenance: str # tool output id
    link: str       # optional URL

OutputStatus = Literal["drafted", "approved", "published", "rejected"]

class ApprovalEntry:
    output_id: str
    decision: Literal["approved", "rejected"]
    by: str         # approver identity
    note: str
    tool_result: str
    date: str

class RunRecord:
    week_key: str       # "YYYY-Www"
    week_of: str        # "YYYY-MM-DD"
    inputs: str
    per_agent: list[str]
    deltas: str
    queued_for_approval: str
    published: str
```

---

## 4. Safety Architecture

| Gate | Location | Mechanism | Enforcement |
|------|----------|-----------|-------------|
| No merge | `github_pr` | No merge endpoint; only `open_pr`/`update_pr` | Structural (no `/merge` path in transport dispatch) |
| Approval-first publish | `social_publish`, `cms_publish` | `approval_token` required; transport untouched without valid token | Code gate before network call |
| Content-hash idempotency | `social_publish` | Content SHA256 dedup prevents double-post | Code gate at adapter level |
| Cost cap | `video_gen` | Quote-first → `check_cap()` → render-only-if-under | Code gate at adapter method level |
| Provenance drop | All agents | Fabricated keys (no evidence in tool output) dropped by type-aware filters | Code gate on agent output |
| Publish gate ordering | `orchestrator` | `PublishGate`: check legality → record approval → fire tool | Code gate in orchestrator |
| URL scheme allowlist | `transports` | `_validate_url_scheme()`: http/https only | Code gate before network fetch |
| Token comparison | `social_publish` | `hmac.compare_digest()` — constant-time | Code gate at adapter level |

---

## 5. Quality & Testing

**206 tests, all pass in ~1.4 s.** Stack: stdlib `unittest` + hand-rolled property tests.

| Category | Tests | Scope |
|----------|-------|-------|
| Unit (adapters, agents, workspace) | 180+ | Per-component invariants, schema, provenance gates |
| Generative PBT | 8 suites (50–150 inputs each) | Adversarial true-negative testing |
| Integration (orchestrator) | 15+ | Fan-out, deltas, publish gate |
| Security (url scheme, token compare) | 7 | Defense-in-depth verification |
| CI pipeline | N/A | ruff, mypy, bandit, tests on push/PR |

**Toolchain:**

| Tool | Result | Gate |
|------|--------|------|
| ruff (lint) | 0 errors | CI |
| mypy (types) | 0 errors (net-new) | CI |
| bandit (SAST) | 0 medium+ | CI |
| unittest (tests) | 206/206 pass | CI |

---

## 6. Configuration

| Env var | Default | Purpose |
|---------|---------|---------|
| `ORION_SEARCH_PROVIDER` | `None` | Search backend (`brave`/`bing`/`serpapi`) |
| `ORION_SEARCH_API_KEY` | `""` | Search API key (behind transport boundary) |
| `ORION_LIGHTHOUSE_CMD` | `npx lighthouse {url} --output=json --quiet --chrome-flags=--headless` | Lighthouse CLI command |
| `ORION_HEADLESS` | `1` | Headless browser mode |
| `CMO_WORKSPACE_ROOT` | `.agents/memory_bank-production/` | Workspace directory |
| `CMO_VIDEO_CAP` | `50` | Per-run video cost cap (USD) |
| `LLM_API_URL` | `https://api.openai.com/v1` | LLM provider base URL |
| `LLM_API_KEY` | `""` | LLM API key |
| `LLM_MODEL` | `gpt-4o` | Model name |
| `LLM_MAX_TOKENS` | `4096` | Max response tokens |

---

## 7. Dependencies

**Runtime:** `fastmcp>=3.4.2` (MCP framework).

**Test only (no runtime install needed):** `ruff`, `mypy`, `bandit` (dev dependency group).

**Live-run optional:** Playwright (`uv run playwright install chromium`), Node + Lighthouse.

---

## 8. Deployment

```bash
# 1. Clone
git clone <repo>
cd orion-os-cmo

# 2. Verify
uv run python -m unittest

# 3. Start MCP server
uv run python -m orion_os_cmo.mcp_server.server

# 4. Configure client
# Add to your MCP client config:
# {
#   "mcpServers": {
#     "orion-cmo": {
#       "command": "uv",
#       "args": ["run", "python", "-m", "orion_os_cmo.mcp_server.server"]
#     }
#   }
# }

# 5. (Optional) Install live-run deps
uv run playwright install chromium     # for scrape
npx lighthouse --help                   # verify lighthouse is available
```

---

## 9. Known Deferrals

1. **Concrete Claude `LLMClient`** — replaced by client-agnostic `HttpLLMClient`. The protocol
   contract is stable; bring your own OpenAI-compatible provider via env vars.
2. **Live end-to-end weekly pass** — requires LLM env vars and first-party API keys for search,
   social, CMS, video, etc. Deferred until operator onboards a client.

---

## 10. License

MIT — see `LICENSE` in project root.
