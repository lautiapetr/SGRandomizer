"""User-facing failures."""


class RandomizerError(RuntimeError):
    """A validation or transformation error safe to show to the user."""


class TransactionError(RandomizerError):
    """A write transaction failed and was rolled back."""
