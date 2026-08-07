from .base import Adapter, AdapterError, PrecomputedAdapter, adapterFor, registry

try:
    from .leamr import LeamrAdapter
    registry[LeamrAdapter.name] = LeamrAdapter
except Exception:
    pass
