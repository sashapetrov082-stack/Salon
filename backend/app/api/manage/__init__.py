from fastapi import APIRouter

from app.api.manage import calendar, catalog, clients, salon, schedule, staff

router = APIRouter(prefix="/manage/{salon_id}", tags=["manage"])
for module in (calendar, schedule, catalog, staff, clients, salon):
    router.include_router(module.router)
