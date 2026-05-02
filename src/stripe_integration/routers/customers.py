from typing import Annotated

import stripe
import structlog
from fastapi import APIRouter, Depends, Header, Request, status

from stripe_integration.auth import verify_api_key
from stripe_integration.limiter import limiter
from stripe_integration.schemas import CreateCustomerRequest, CustomerResponse
from stripe_integration.stripe_client import get_stripe_client, stripe_call

logger = structlog.get_logger()
router = APIRouter(
    prefix="/customers",
    tags=["customers"],
    dependencies=[Depends(verify_api_key)],
)


def _serialize_customer(c: stripe.Customer) -> CustomerResponse:
    return CustomerResponse(
        id=c.id,
        email=c.email,
        name=c.name,
        metadata=dict(c.metadata) if c.metadata else {},
        created=c.created,
    )


@router.post("", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def create_customer(
    request: Request,
    body: CreateCustomerRequest,
    idempotency_key: Annotated[str | None, Header()] = None,
    client: stripe.StripeClient = Depends(get_stripe_client),
) -> CustomerResponse:
    params: dict = {"email": body.email}
    if body.name:
        params["name"] = body.name
    if body.metadata:
        params["metadata"] = body.metadata

    kwargs: dict = {"params": params}
    if idempotency_key:
        kwargs["options"] = {"idempotency_key": idempotency_key}

    customer = await stripe_call(client.v1.customers.create, **kwargs)
    logger.info("customer_created", customer_id=customer.id)
    return _serialize_customer(customer)


@router.get("/{customer_id}", response_model=CustomerResponse)
@limiter.limit("30/minute")
async def get_customer(
    request: Request,
    customer_id: str,
    client: stripe.StripeClient = Depends(get_stripe_client),
) -> CustomerResponse:
    customer = await stripe_call(client.v1.customers.retrieve, customer_id)
    return _serialize_customer(customer)
