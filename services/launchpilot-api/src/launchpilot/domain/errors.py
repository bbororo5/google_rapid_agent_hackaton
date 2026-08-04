class DomainError(ValueError):
    """Raised when a domain invariant is violated."""


class NotFoundError(LookupError):
    """Raised when an entity does not exist in its repository."""
