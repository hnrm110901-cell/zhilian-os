"""
Custom exceptions for the application
"""


class NotFoundError(Exception):
    """Resource not found exception"""
    pass


class ValidationError(Exception):
    """Validation error exception"""
    pass


class AuthenticationError(Exception):
    """Authentication error exception"""
    pass


class AuthorizationError(Exception):
    """Authorization error exception"""
    pass
