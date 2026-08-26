from typing import Annotated

from fastapi import Depends, Request

from app.core.config import Settings, get_settings
from app.services.contact import ContactService
from app.services.hevy.client import HevyClient
from app.services.hevy.snapshot import HevySnapshotService

SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_contact_service(settings: SettingsDep) -> ContactService:
    return ContactService(settings)


ContactServiceDep = Annotated[ContactService, Depends(get_contact_service)]


def get_hevy_client(settings: SettingsDep) -> HevyClient:
    return HevyClient(settings)


HevyClientDep = Annotated[HevyClient, Depends(get_hevy_client)]


def get_hevy_snapshot_service(settings: SettingsDep, client: HevyClientDep) -> HevySnapshotService:
    return HevySnapshotService(settings, client)


HevySnapshotServiceDep = Annotated[HevySnapshotService, Depends(get_hevy_snapshot_service)]


def get_client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


ClientIpDep = Annotated[str, Depends(get_client_ip)]
