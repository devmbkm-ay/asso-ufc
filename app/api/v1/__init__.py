from fastapi import APIRouter
from app.api.v1.routes import auth, members, cotisations, events, notifications, collectes

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(members.router)
api_router.include_router(cotisations.router)
api_router.include_router(events.router)
api_router.include_router(notifications.router)
api_router.include_router(collectes.router)
