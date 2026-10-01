from fastapi import APIRouter

from netmon.api.v1 import alerts, analytics, auth, devices, discovery, system, topology, users

api_router = APIRouter()
for module in (auth, users, devices, discovery, topology, alerts, analytics, system):
    api_router.include_router(module.router)
