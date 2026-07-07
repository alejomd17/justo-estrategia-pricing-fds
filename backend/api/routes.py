from datetime import date

import pandas as pd
from fastapi import APIRouter, Depends

from backend.api.deps import get_cursor
from backend.api.serialization import df_to_records
from backend.pricing import postmortem

router = APIRouter()


@router.get("/health")
def health(cur=Depends(get_cursor)):
    cur.execute("SELECT 1")
    cur.fetchone()
    return {"status": "ok"}


@router.get("/campaigns")
def list_campaigns(cur=Depends(get_cursor)):
    return df_to_records(postmortem.listar_campanas(cur))


@router.get("/campaigns/{campaign_start}/{campaign_end}/summary")
def campaign_summary(campaign_start: date, campaign_end: date, cur=Depends(get_cursor)):
    start, end = pd.Timestamp(campaign_start), pd.Timestamp(campaign_end)
    por_origen = df_to_records(postmortem.resumen_adopcion(cur, start, end))
    total_planeado = postmortem.contar_plan(cur, start, end)
    wknd = next((r for r in por_origen if r["ORIGEN_CAMPANA"] == "WKND"), None)
    adopcion_pct = (
        round(wknd["SKU_TIENDAS_CON_PROMO_REAL"] / total_planeado * 100, 1)
        if wknd and total_planeado
        else None
    )
    return {"por_origen": por_origen, "total_planeado": total_planeado, "adopcion_pct": adopcion_pct}


@router.get("/campaigns/{campaign_start}/{campaign_end}/mechanics")
def campaign_mechanics(campaign_start: date, campaign_end: date, cur=Depends(get_cursor)):
    df = postmortem.performance_por_mecanica(cur, pd.Timestamp(campaign_start), pd.Timestamp(campaign_end))
    return df_to_records(df)


@router.get("/campaigns/{campaign_start}/{campaign_end}/redemption")
def campaign_redemption(campaign_start: date, campaign_end: date, cur=Depends(get_cursor)):
    df = postmortem.validar_redencion_real(cur, pd.Timestamp(campaign_start), pd.Timestamp(campaign_end))
    return df_to_records(df)
