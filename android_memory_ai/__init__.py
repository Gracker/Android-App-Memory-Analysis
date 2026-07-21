"""Provider-neutral evidence contracts for Android memory AI workflows."""

from .context import build_ai_context
from .contracts import RUNTIME_VERSION

__all__ = ["build_ai_context"]
__version__ = RUNTIME_VERSION
