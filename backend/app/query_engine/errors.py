from __future__ import annotations


class DomainPackError(Exception):
    """Base error for domain pack loading failures."""


class DomainPackValidationError(DomainPackError):
    """Raised when a domain pack is missing required data or is malformed."""

