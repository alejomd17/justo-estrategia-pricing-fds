"""Crea la estrategia de ofertas de un fin de semana FUTURO y sube el plan
a Snowflake, de una sola corrida (sin notebook):

    uv run run_estrategias.py                          # proximo viernes-domingo
    uv run run_estrategias.py --inicio 2026-07-18 --fin 2026-07-20

Hace, en orden: construir_estrategia (elegibilidad, score, mecanica,
guardrail, escenarios, Excel en data/output/) -> subir el plan a
SANDBOX.WKND_PROMO_PLAN + recrear vistas + materializar -> resumen en
consola.

Se niega a correr para una ventana que ya paso (eso pisaria el registro
historico del plan real ejecutado) - para medir una campana pasada usar
run_postmortem.py; para subir un Excel real con formato raro (ej. hojas
GENRAL/Cervezas/Limpieza de la campana 11-13 jul), el notebook.
"""

import argparse

import pandas as pd

from backend.pricing import postmortem, strategy
from backend.pricing.snowflake_conn import get_connection


def proximo_finde() -> tuple[pd.Timestamp, pd.Timestamp]:
    """Proximo viernes-domingo (si hoy es viernes, este mismo finde)."""
    hoy = pd.Timestamp.now().normalize()
    dias_al_viernes = (4 - hoy.weekday()) % 7  # weekday(): lunes=0 ... viernes=4
    inicio = hoy + pd.Timedelta(days=dias_al_viernes)
    return inicio, inicio + pd.Timedelta(days=2)


def imprimir_resumen(df: pd.DataFrame) -> None:
    """Mismo resumen que la celda 'Resultados finales' del notebook."""
    ofer = df[df["MECANICA"] != "Sin oferta"]

    print("\n=== ESTRATEGIA ===")
    print(df["MECANICA"].value_counts().to_string())
    print(f"\nOfertas: {len(ofer)} de {len(df)} ({len(ofer) / len(df) * 100:.1f}%) | "
          f"descuento exhibido promedio: {ofer['DESC_EFECTIVO'].mean() * 100:.1f}% | "
          f"margen minimo en promocion: {ofer['MARGEN_OFERTA'].min():.2f}%")
    print(f"SKUs que requieren aprobacion Comercial (no incluidos, d_max real > 30%): "
          f"{df['REQUIERE_APROBACION'].sum()}")

    print("\n=== PROYECCION ESCENARIO BASE ===")
    print(f"Unidades: {ofer['Q0_DIA'].sum():,.0f} -> {ofer['Q1_DIA'].sum():,.0f} "
          f"({(ofer['Q1_DIA'].sum() / ofer['Q0_DIA'].sum() - 1) * 100:+.1f}%)")
    print(f"GMV:      ${ofer['GMV_BASE_DIA'].sum():,.0f} -> ${ofer['GMV_PROY_DIA'].sum():,.0f} "
          f"({(ofer['GMV_PROY_DIA'].sum() / ofer['GMV_BASE_DIA'].sum() - 1) * 100:+.1f}%)")
    print(f"Utilidad: ${ofer['UTIL_BASE_DIA'].sum():,.0f} -> ${ofer['UTIL_PROY_DIA'].sum():,.0f} "
          f"({(ofer['UTIL_PROY_DIA'].sum() / ofer['UTIL_BASE_DIA'].sum() - 1) * 100:+.1f}%)")

    print("\n=== POR DIA ===")
    print(ofer.groupby("DIA_EJECUCION").agg(Ofertas=("SKU", "count"),
          GMV_inc=("GMV_INC_DIA", "sum"), Util_inc=("UTIL_INC_DIA", "sum")).round(0).to_string())

    print("\n=== CONFIANZA DE LA PROYECCION (ofertas finales) ===")
    print(ofer["CONFIANZA_PROYECCION"].value_counts().to_string())

    mun = ofer[ofer["TEMA_MUNDIAL"]]
    print(f"\n=== MUNDIAL ===\nOfertas: {len(mun)} | GMV incremental: ${mun['GMV_INC_DIA'].sum():,.0f} | "
          f"Utilidad incremental: ${mun['UTIL_INC_DIA'].sum():,.0f}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Crea la estrategia FDS y sube el plan (finde futuro)")
    parser.add_argument("--inicio", help="YYYY-MM-DD (default: proximo viernes)")
    parser.add_argument("--fin", help="YYYY-MM-DD (default: inicio + 2 dias)")
    parser.add_argument("--ruta-oportunidad", default="data/inputs/oportunidad.xlsx")
    parser.add_argument("--ruta-descuentos", default="data/inputs/Descuentos comerciales.xlsx")
    parser.add_argument("--sin-subir", action="store_true",
                        help="Solo genera el Excel, no sube el plan a Snowflake")
    args = parser.parse_args()

    if args.inicio:
        weekend_inicio = pd.Timestamp(args.inicio)
        weekend_fin = pd.Timestamp(args.fin) if args.fin else weekend_inicio + pd.Timedelta(days=2)
    else:
        weekend_inicio, weekend_fin = proximo_finde()

    if not postmortem.plan_aun_no_ejecutado(weekend_fin):
        raise SystemExit(
            f"La ventana {weekend_inicio.date()} a {weekend_fin.date()} ya paso - no se construye "
            "una estrategia nueva para una campana ya ejecutada (pisaria el registro historico). "
            "Para medirla: uv run run_postmortem.py"
        )

    ruta_salida = strategy.generar_ruta_salida(weekend_inicio, weekend_fin, carpeta="data/output")
    print(f"Fin de semana objetivo: {weekend_inicio.date()} a {weekend_fin.date()}")
    print(f"Excel de salida: {ruta_salida}")

    print("\nConectando a Snowflake (completa el login en el navegador si se abre)...")
    conn = get_connection()
    cur = conn.cursor()

    try:
        df = strategy.construir_estrategia(
            cur=cur,
            ruta_oportunidad=args.ruta_oportunidad,
            ruta_descuentos=args.ruta_descuentos,
            ruta_salida=ruta_salida,
            weekend_inicio=weekend_inicio,
            weekend_fin=weekend_fin,
        )

        if args.sin_subir:
            print("\n--sin-subir: el plan NO se subio a Snowflake.")
        else:
            estrategia_df = df[df["MECANICA"] != "Sin oferta"].rename(columns={"MARGEN_OFERTA": "MARGEN_OFERTA_%"})
            n = postmortem.subir_plan_y_crear_vistas(cur, estrategia_df, weekend_inicio, weekend_fin)
            print(f"\nPlan subido a SANDBOX.WKND_PROMO_PLAN: {n} filas "
                  "(finde aun no ejecutado, se sobreescribe en cada corrida)")

        imprimir_resumen(df)
        print(f"\nListo. Excel en: {ruta_salida}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
