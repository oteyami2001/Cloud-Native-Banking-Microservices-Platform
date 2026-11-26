"""Resolve the authenticated principal to a server-side customer id.

The customer id is **never** taken from the request. It is looked up from the
identity pointer item owned by the customer service::

    PK = IDENTITY#<cognito sub>   SK = CUSTOMER   customer_id = CUS-...

Other services are granted ``dynamodb:GetItem`` on the customers table only
for leading keys matching ``IDENTITY#*`` (see terraform/modules/lambda-service).
"""

from __future__ import annotations

from shared import aws
from shared.auth import Principal
from shared.config import tables
from shared.errors import ForbiddenError


def customer_id_for(principal: Principal, *, required: bool = True) -> str | None:
    item = (
        aws.table(tables().customers)
        .get_item(Key={"PK": f"IDENTITY#{principal.subject}", "SK": "CUSTOMER"}, ConsistentRead=True)
        .get("Item")
    )
    if not item:
        if required:
            raise ForbiddenError("Customer profile has not been created for this identity")
        return None
    if item.get("status", "ACTIVE") != "ACTIVE":
        raise ForbiddenError("Customer profile is not active")
    return str(item["customer_id"])
