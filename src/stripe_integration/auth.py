from typing import Annotated

from fastapi import Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from stripe_integration.config import get_settings
from stripe_integration.exceptions import UnauthorizedError

_bearer = HTTPBearer(auto_error=False)


async def verify_api_key(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Security(_bearer)
    ] = None,
) -> None:
    settings = get_settings()
    if credentials is None or credentials.credentials != settings.api_key:
        raise UnauthorizedError()
