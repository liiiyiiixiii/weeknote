"""Compatibility alias for ephemeral runtime-state persistence."""

import sys

from app.persistence import runtime_backend as _implementation

sys.modules[__name__] = _implementation
