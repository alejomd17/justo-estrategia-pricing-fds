"""Dashboard API - post-mortem de campanas FDS.

Correr desde la raiz del repo (para que `backend` se resuelva como paquete):

    uv run uvicorn backend.api.main:app --reload --port 8000

Abre el navegador para completar el login SSO una sola vez al arrancar -
la conexion se mantiene viva mientras el proceso corra (ver Fase 4 del plan
en /home/alejomd17/.claude/plans/vamos-a-cambiar-de-glowing-plum.md). v1
pensada solo para correr localmente.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes import router
from backend.pricing.snowflake_conn import get_connection


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Abriendo conexion SSO a Snowflake - completa el login en el navegador si se abre...")
    app.state.conn = get_connection()
    print("Conexion abierta.")
    yield
    app.state.conn.close()


app = FastAPI(title="Estrategia Pricing FDS - Dashboard API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")
