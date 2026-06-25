# Contributing

## Prerequisites

- Python 3.11+ (managed by `uv`)
- `uv` installed (`curl -LsSf https://astral.sh/uv/install.sh | sh`)

## Setup

```bash
git clone <repo>
cd orion-os-cmo
uv run python -m unittest discover -s tests   # verify everything works
```

## Development workflow

1. **Write tests** — stdlib `unittest`, in `tests/`. Name files `test_<name>.py`.
2. **Run the suite** — `uv run python -m unittest discover -s tests`. All must pass.
3. **Lint** — `uvx ruff check orion_os_cmo tests`. Zero errors required.
4. **Types** — `uvx mypy orion_os_cmo --ignore-missing-imports`. Zero net-new errors.
5. **SAST** — `uvx bandit -r orion_os_cmo -ll`. No medium+ findings.

All four gates run in CI on every push/PR. Keep them green.

## Code conventions

- Match existing style: frozen dataclass contracts, `Ok`/`Err` results, `__future__` annotations.
- No `Any` unless the value can truly be any type.
- All I/O behind the `Transport` seam — adapters never see secrets.
- Every factual claim must trace to a tool output. No invented data.

## Project structure

```
orion_os_cmo/
  adapters/          # Tool façades over the Transport seam
  agent_*/           # Strategy-conditioned drafting agents
  orchestrator/      # Weekly pass coordinator + brief assembly
  client_workspace/  # Per-client durable store
  strategy_store/    # Root artifact builder
  transports/        # Injectable data backends
  llm/               # LLM client protocol + implementations
  mcp_server/        # Client-agnostic MCP server
  common/            # Shared types (Result, etc.)
```

## Need help?

Open an issue or start a discussion. See the `docs/` directory for detailed specs.
