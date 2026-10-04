"""Domain errors, mapped to HTTP responses in main.py.

Services raise these instead of HTTPException so the business logic stays independent
of the web layer (and is easy to call from the CLI and tests).
"""


class DomainError(Exception):
    status_code = 400
    code = "bad_request"

    def __init__(self, message: str, *, details: object | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class Unauthorized(DomainError):
    status_code = 401
    code = "unauthorized"


class Forbidden(DomainError):
    status_code = 403
    code = "forbidden"


class NotFound(DomainError):
    status_code = 404
    code = "not_found"


class Conflict(DomainError):
    """The request is well-formed but violates a business rule in the current state."""

    status_code = 409
    code = "conflict"


class InvalidInput(DomainError):
    status_code = 422
    code = "invalid_input"


class PayloadTooLarge(DomainError):
    status_code = 413
    code = "payload_too_large"
