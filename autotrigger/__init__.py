"""mcp-graphify-autotrigger - auto-trigger graphify queries + delegate shell."""
from . import classifier
from . import graphify
from . import preflight
from . import delegate

__version__ = "0.1.0"
__all__ = ["classifier", "graphify", "preflight", "delegate", "__version__"]
