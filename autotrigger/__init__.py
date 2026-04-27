"""mcp-graphify-autotrigger - auto-trigger graphify queries + delegate shell + auto-cleanup."""
from . import classifier
from . import graphify
from . import preflight
from . import delegate
from . import cleanup

__version__ = "0.2.1"
__all__ = ["classifier", "graphify", "preflight", "delegate", "cleanup", "__version__"]

