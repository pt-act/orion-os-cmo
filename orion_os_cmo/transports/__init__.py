"""Self-hosted / own-key data transports (ADR #7).

Concrete implementations of the shared ``Transport`` protocol that run the data
path on the operator's own infrastructure — no paid aggregator behind the seam.
Importing this package is install-free; heavy deps (Playwright, Lighthouse, search
HTTP) are imported lazily inside the relevant handler.
"""

from __future__ import annotations

from .config import (
    SearchNotConfiguredError,
    TransportConfig,
    TransportRunError,
    UnsupportedPathError,
)
from .self_hosted import SelfHostedTransport

__all__ = [
    "SelfHostedTransport",
    "TransportConfig",
    "UnsupportedPathError",
    "SearchNotConfiguredError",
    "TransportRunError",
]
