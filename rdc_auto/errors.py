from __future__ import annotations


class RdcAutoError(Exception):
    """Base exception for expected rdc-auto failures."""


class UserActionRequired(RdcAutoError):
    """Raised when the CLI must ask the user before continuing."""


class DependencyMissing(RdcAutoError):
    """Raised when a required local dependency cannot be found."""


class McpCapabilityMissing(RdcAutoError):
    """Raised when RenderDocMCP does not expose a required tool."""
