"""Synchronous service-to-service clients.

In AWS each service is a separate Lambda function and synchronous calls use
``lambda:InvokeFunction`` restricted by IAM to the specific callee. Locally (and
in tests) the same contract is satisfied in-process, which keeps every service
independently testable while exercising the real request/response payloads.

Internal payload contract::

    request  {"action": "<name>", "payload": {...}, "correlation_id": "..."}
    response {"ok": true, "result": {...}} | {"ok": false, "error": {...}}
"""

from __future__ import annotations

import importlib
import json
import os
from typing import Any

from shared import aws, errors
from shared.errors import BankingError, DependencyUnavailableError
from shared.logging import get_correlation_id

_ERRORS: dict[str, type[BankingError]] = {
    cls.code: cls
    for cls in vars(errors).values()
    if isinstance(cls, type) and issubclass(cls, BankingError)
}

_LOCAL_MODULES = {
    "ledger": "services.ledger.handler",
    "fraud": "services.fraud.handler",
    "account": "services.account.handler",
}

#: Test hook: service name -> callable used instead of the real dependency.
OVERRIDES: dict[str, Any] = {}


def _raise_remote(error: dict[str, Any]) -> None:
    cls = _ERRORS.get(error.get("code", ""), BankingError)
    raise cls(error.get("message"), details=error.get("details"))


class ServiceClient:
    def __init__(self, service: str):
        self.service = service

    def call(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        request = {"action": action, "payload": payload, "correlation_id": get_correlation_id()}
        try:
            reply = self._dispatch(request)
        except BankingError:
            raise
        except Exception as exc:  # noqa: BLE001 - any transport failure fails closed
            raise DependencyUnavailableError(f"{self.service} service unavailable") from exc
        if not isinstance(reply, dict) or "ok" not in reply:
            raise DependencyUnavailableError(f"{self.service} service returned an invalid response")
        if not reply["ok"]:
            _raise_remote(reply.get("error", {}))
        return reply["result"]

    def _dispatch(self, request: dict[str, Any]) -> Any:
        if self.service in OVERRIDES:
            return OVERRIDES[self.service](request)
        function_name = os.environ.get(f"{self.service.upper()}_FUNCTION_NAME")
        if not function_name:
            module = importlib.import_module(_LOCAL_MODULES[self.service])
            # Round-trip through JSON so local calls see exactly what Lambda would.
            return json.loads(json.dumps(module.internal(json.loads(json.dumps(request)))))
        result = aws.client("lambda").invoke(
            FunctionName=function_name,
            InvocationType="RequestResponse",
            Payload=json.dumps(request).encode(),
        )
        if result.get("FunctionError"):
            raise DependencyUnavailableError(f"{self.service} function error")
        return json.loads(result["Payload"].read())


def internal_dispatch(actions: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    """Server side of the internal contract, used by each service's ``internal``."""

    from shared.logging import set_correlation_id

    set_correlation_id(request.get("correlation_id"))
    action = actions.get(request.get("action"))
    if action is None:
        return {"ok": False, "error": {"code": "VALIDATION_ERROR", "message": "Unknown action"}}
    try:
        return {"ok": True, "result": action(request.get("payload") or {})}
    except BankingError as err:
        return {"ok": False, "error": err.to_body()["error"]}


def ledger() -> ServiceClient:
    return ServiceClient("ledger")


def fraud() -> ServiceClient:
    return ServiceClient("fraud")


def account() -> ServiceClient:
    return ServiceClient("account")
