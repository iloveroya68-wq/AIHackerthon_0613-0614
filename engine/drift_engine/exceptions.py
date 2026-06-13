class DriftEngineError(RuntimeError):
    """Base error raised by the real drift engine."""


class DriftSimulationError(DriftEngineError):
    """The L2 particle simulation failed or returned no usable particles."""


class ModelSchemaError(DriftEngineError):
    """The L3 artifact does not match the runtime feature schema."""
