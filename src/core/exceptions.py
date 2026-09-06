from src.schemas.common import BusinessErrorCode


class BusinessException(Exception):
    """Raised for catalog business failures that map to BusinessError JSON bodies."""

    def __init__(self, status_code: int, code: BusinessErrorCode, message: str) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(message)
