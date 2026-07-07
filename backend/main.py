"""Orquestador CLI:

    uv run python -m backend.main strategy --weekend-inicio 2026-07-10 --weekend-fin 2026-07-12
    uv run python -m backend.main postmortem --campaign-inicio 2026-07-03 --campaign-fin 2026-07-05

Correr desde la raiz del proyecto (para que `backend` se resuelva como
paquete). Usa la conexion SSO (`pricing.snowflake_conn`) - requiere completar
el login por navegador cuando lo pida.
"""

import argparse

import pandas as pd

from backend.pricing import postmortem, strategy
from backend.pricing.snowflake_conn import get_connection


def cmd_strategy(args):
    conn = get_connection()
    cur = conn.cursor()
    weekend_inicio = pd.Timestamp(args.weekend_inicio)
    weekend_fin = pd.Timestamp(args.weekend_fin)

    df = strategy.construir_estrategia(
        cur=cur,
        ruta_oportunidad=args.ruta_oportunidad,
        ruta_descuentos=args.ruta_descuentos,
        ruta_salida=args.ruta_salida,
        weekend_inicio=weekend_inicio,
        weekend_fin=weekend_fin,
    )

    if args.subir_plan:
        if not postmortem.plan_aun_no_ejecutado(weekend_fin):
            print(
                "weekend-fin ya paso - no se sube automaticamente para no pisar "
                "el plan real ejecutado. Usa `postmortem` con el Excel real desde disco."
            )
        else:
            estrategia_df = df[df["MECANICA"] != "Sin oferta"].rename(
                columns={"MARGEN_OFERTA": "MARGEN_OFERTA_%"}
            )
            n = postmortem.subir_plan_y_crear_vistas(cur, estrategia_df, weekend_inicio, weekend_fin)
            print(f"Plan subido a SANDBOX.WKND_PROMO_PLAN: {n} filas")


def cmd_postmortem(args):
    conn = get_connection()
    cur = conn.cursor()
    campaign_inicio = pd.Timestamp(args.campaign_inicio)
    campaign_fin = pd.Timestamp(args.campaign_fin)

    print("Creando/actualizando vistas de post-mortem en SANDBOX...")
    postmortem.crear_objetos_postmortem(cur)

    resumen = postmortem.performance_por_mecanica(cur, campaign_inicio, campaign_fin)
    print(resumen.to_string(index=False))


def main():
    parser = argparse.ArgumentParser(description="Estrategia de precios FDS - orquestador")
    sub = parser.add_subparsers(dest="comando", required=True)

    p_strategy = sub.add_parser("strategy", help="Arma la estrategia de un proximo fin de semana")
    p_strategy.add_argument("--weekend-inicio", required=True, help="YYYY-MM-DD (viernes)")
    p_strategy.add_argument("--weekend-fin", required=True, help="YYYY-MM-DD (domingo)")
    p_strategy.add_argument("--ruta-oportunidad", default="data/inputs/oportunidad.xlsx")
    p_strategy.add_argument("--ruta-descuentos", default="data/inputs/Descuentos comerciales.xlsx")
    p_strategy.add_argument("--ruta-salida", default="data/output/estrategia_fds.xlsx")
    p_strategy.add_argument(
        "--subir-plan", action="store_true", help="Ademas sube el plan a SANDBOX.WKND_PROMO_PLAN"
    )
    p_strategy.set_defaults(func=cmd_strategy)

    p_postmortem = sub.add_parser("postmortem", help="Mide una promo que ya corrio")
    p_postmortem.add_argument("--campaign-inicio", required=True, help="YYYY-MM-DD")
    p_postmortem.add_argument("--campaign-fin", required=True, help="YYYY-MM-DD")
    p_postmortem.set_defaults(func=cmd_postmortem)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
