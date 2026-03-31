from fastapi import APIRouter

from shopper.api.routes.runs import router as runs_router
from shopper.api.routes.users import router as users_router


router = APIRouter()
router.include_router(runs_router)
router.include_router(users_router)

__all__ = ["router"]
