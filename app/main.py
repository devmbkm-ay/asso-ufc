from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.tasks import start_scheduler, stop_scheduler
from app.api.v1 import api_router

UPLOAD_DIR = Path("/app/uploads")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Code avant "yield" : exécuté au démarrage du serveur
    start_scheduler()
    yield
    # Code après "yield" : exécuté à l'arrêt propre du serveur
    stop_scheduler()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/docs",       # Swagger UI interactif
    redoc_url="/redoc",     # Documentation alternative ReDoc
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
# CORS (Cross-Origin Resource Sharing) : autorise le frontend (ex: localhost:3000)
# à appeler cette API depuis un navigateur, malgré les restrictions de sécurité
# imposées par les navigateurs sur les requêtes entre domaines différents.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routes ────────────────────────────────────────────────────────────────────
app.include_router(api_router)

# ── Fichiers statiques (photos uploadées) ─────────────────────────────────────
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")


@app.get("/health", tags=["System"])
def health():
    # Endpoint de vérification utilisé par les outils de monitoring et
    # les health checks Docker/Kubernetes pour savoir si l'API est vivante.
    return {"status": "ok", "version": settings.APP_VERSION}


import logging

logger = logging.getLogger(__name__)

# ── Gestion globale des erreurs ───────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception on %s %s", request.method, request.url)
    # On ajoute manuellement les headers CORS car quand une exception non
    # gérée remonte jusqu'ici, le CORSMiddleware ne peut plus les injecter.
    origin = request.headers.get("origin", "")
    cors_headers = {}
    if origin in settings.ALLOWED_ORIGINS:
        cors_headers["Access-Control-Allow-Origin"] = origin
        cors_headers["Access-Control-Allow-Credentials"] = "true"
    return JSONResponse(
        status_code=500,
        content={"detail": "Erreur interne du serveur"},
        headers=cors_headers,
    )
