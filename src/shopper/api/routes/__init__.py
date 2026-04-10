from fastapi import APIRouter

from shopper.api.routes.checkout_profiles import router as checkout_profiles_router
from shopper.api.routes.inventory import router as inventory_router
from shopper.api.routes.runs import router as runs_router
from shopper.api.routes.stream import router as stream_router
from shopper.api.routes.users import router as users_router
from shopper.supplements.api import router as supplements_router


router = APIRouter()
router.include_router(checkout_profiles_router)
router.include_router(inventory_router)
router.include_router(runs_router)
router.include_router(stream_router)
router.include_router(supplements_router)
router.include_router(users_router)

__all__ = ["router"]
