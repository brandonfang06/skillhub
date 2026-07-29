"""Public error types for scanner adapter callers."""


class ScannerAdapterError(Exception):
    """Base class for expected adapter failures."""


class ConfigurationError(ScannerAdapterError):
    """Configuration is invalid."""


class InputValidationError(ScannerAdapterError):
    """The supplied ZIP path is invalid."""


class ScannerUnavailableError(ScannerAdapterError):
    """The scanner could not be reached or timed out."""


class ScannerHttpError(ScannerAdapterError):
    """The scanner returned a non-success HTTP response."""


class ScannerResponseError(ScannerAdapterError):
    """The scanner returned invalid JSON or an incompatible payload."""
