"""Compatibility alias for the persistent domain storage implementation."""

import sys

from app.persistence import storage_backend as _implementation

sys.modules[__name__] = _implementation
