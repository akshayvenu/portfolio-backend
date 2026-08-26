from fastapi import APIRouter, status

from app.api.deps import ClientIpDep, ContactServiceDep
from app.schemas.contact import ContactRequest, ContactResponse

router = APIRouter(tags=["contact"])


@router.post("/contact", response_model=ContactResponse, status_code=status.HTTP_201_CREATED)
async def submit_contact_form(
    payload: ContactRequest,
    contact_service: ContactServiceDep,
    client_ip: ClientIpDep,
) -> ContactResponse:
    return contact_service.submit(payload, client_ip)
