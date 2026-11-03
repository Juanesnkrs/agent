"""Provider errors."""


class ProviderError(RuntimeError):
    """Raised when a provider cannot produce usable odds."""


class ProviderBlockedError(ProviderError):
    """The bookmaker answered with a block (403, 429, captcha or challenge).

    The caller must stop using that bookmaker for the rest of the run and must
    not retry or try to evade the block.
    """


class ProviderUnavailableError(ProviderError):
    """The bookmaker could not be reached after the allowed retries."""

