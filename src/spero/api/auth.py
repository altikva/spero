# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-07
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (https://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: Bearer-token auth dependency shared by the serve and owner HTTP surfaces.

"""A shared bearer-token dependency for the control-plane and owner APIs.

Both surfaces are optionally protected by a static token. When the configured
token is empty, auth is disabled (the right default for a localhost `serve`); when
it is set, every guarded route requires ``Authorization: Bearer <token>``, compared
in constant time. ``/health`` is always left unguarded so a kubelet probe still
works. TLS is expected to terminate at an ingress in front of the service.
"""

from __future__ import annotations

import hmac
from collections.abc import Awaitable, Callable

from fastapi import Header, HTTPException

# A FastAPI dependency: raises 401 on a bad token, returns None when it passes.
AuthDependency = Callable[[str], Awaitable[None]]


def make_auth_dependency(token: str) -> AuthDependency:
    """Build a dependency that enforces ``Authorization: Bearer <token>``.

    With an empty ``token`` the dependency is a no-op (auth disabled).
    """

    async def _check(authorization: str = Header(default="")) -> None:
        if not token:
            return  # auth disabled
        if not hmac.compare_digest(authorization, f"Bearer {token}"):
            raise HTTPException(
                status_code=401,
                detail="missing or invalid bearer token",
                headers={"WWW-Authenticate": "Bearer"},
            )

    return _check
