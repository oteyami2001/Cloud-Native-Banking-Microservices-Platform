"""Principal extraction and authorization for API Gateway HTTP API events.

Signature, expiry, issuer and audience/client_id are validated by the API
Gateway JWT authorizer before the Lambda function is invoked. This module adds
defense in depth: it re-checks the issuer, token use and client id against
expected configuration, enforces OAuth scopes and Cognito groups, and never
trusts identity supplied in a request body or path.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any

from shared.errors import AuthenticationError, ForbiddenError

SCOPE_READ = "novabank/read"
SCOPE_WRITE = "novabank/write"
SCOPE_ADMIN = "novabank/admin"

GROUP_CUSTOMERS = "customers"
GROUP_FRAUD_REVIEWERS = "fraud-reviewers"
GROUP_AUDITORS = "auditors"


@dataclass(frozen=True)
class Principal:
    subject: str
    username: str
    scopes: frozenset[str] = field(default_factory=frozenset)
    groups: frozenset[str] = field(default_factory=frozenset)

    def require_scope(self, scope: str) -> None:
        if scope not in self.scopes:
            raise ForbiddenError("Token is missing a required scope", details={"required_scope": scope})

    def require_group(self, *groups: str) -> None:
        if not self.groups.intersection(groups):
            raise ForbiddenError("Caller is not a member of an authorized group")

    def is_member(self, group: str) -> bool:
        return group in self.groups


def _split_claim(value: Any) -> frozenset[str]:
    """Normalise list claims.

    HTTP API passes array claims as strings such as ``"[a b]"`` or ``"[a, b]"``.
    """

    if value is None:
        return frozenset()
    if isinstance(value, list | tuple | set | frozenset):
        return frozenset(str(v) for v in value)
    text = str(value).strip()
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1]
    return frozenset(part for part in text.replace(",", " ").split() if part)


def principal_from_event(event: dict[str, Any]) -> Principal:
    claims = event.get("requestContext", {}).get("authorizer", {}).get("jwt", {}).get("claims")
    if not isinstance(claims, dict) or not claims.get("sub"):
        raise AuthenticationError("Missing or invalid access token")

    expected_issuer = os.environ.get("EXPECTED_ISSUER")
    if expected_issuer and claims.get("iss") != expected_issuer:
        raise AuthenticationError("Token issuer is not trusted")

    allowed_clients = _split_claim(os.environ.get("ALLOWED_CLIENT_IDS"))
    if allowed_clients:
        client_id = claims.get("client_id") or claims.get("aud")
        if client_id not in allowed_clients:
            raise AuthenticationError("Token audience is not trusted")

    if claims.get("token_use", "access") != "access":
        raise AuthenticationError("An access token is required")

    exp = claims.get("exp")
    if exp is not None:
        try:
            if int(exp) < int(time.time()):
                raise AuthenticationError("Token has expired")
        except (TypeError, ValueError) as exc:
            raise AuthenticationError("Malformed token expiry") from exc

    return Principal(
        subject=str(claims["sub"]),
        username=str(claims.get("username") or claims.get("cognito:username") or claims["sub"]),
        scopes=_split_claim(claims.get("scope")),
        groups=_split_claim(claims.get("cognito:groups")),
    )
