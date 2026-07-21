"""Post-mortem completo de una campana ya ejecutada, de una sola corrida
(sin notebook):

    uv run run_postmortem.py                              # ultima campana subida
    uv run run_postmortem.py --inicio 2026-07-11 --fin 2026-07-13
    uv run run_postmortem.py --origen "" --adopcion ""    # sin filtros (ver TODO)

Asume que el plan de la campana YA esta en SANDBOX.WKND_PROMO_PLAN (lo sube
run_estrategias.py para findes futuros; para un Excel real con formato raro
- ej. las hojas GENRAL/Cervezas/Limpieza del 11-13 jul - usar el notebook).

Hace, en orden: refrescar la tabla materializada -> todas las mediciones
(mecanica, adopcion, top SKUs, plataforma, tipo de cliente, cruces,
usuarios distintos) -> resumen en consola -> reporte HTML autonomo en
data/output/ (mismas secciones que el dashboard).
"""

import argparse

import pandas as pd

from backend.pricing import postmortem
from backend.pricing.snowflake_conn import get_connection


def main() -> None:
    parser = argparse.ArgumentParser(description="Post-mortem completo de una campana FDS ya ejecutada")
    parser.add_argument("--inicio", help="YYYY-MM-DD (default: la ultima campana subida al plan)")
    parser.add_argument("--fin", help="YYYY-MM-DD")
    parser.add_argument("--origen", default="WKND",
                        help='Filtro ORIGEN_CAMPANA (default "WKND"; pasar "" para ver todo)')
    parser.add_argument("--adopcion", default="con_mecanica",
                        help='Filtro de adopcion (default "con_mecanica"; pasar "" para ver todo)')
    parser.add_argument("--sin-refrescar", action="store_true",
                        help="No re-materializa la tabla de post-mortem (mas rapido si acabas de subir el plan)")
    args = parser.parse_args()

    origen = args.origen or None
    adopcion = args.adopcion or None

    print("Conectando a Snowflake (completa el login en el navegador si se abre)...")
    conn = get_connection()
    cur = conn.cursor()

    try:
        if args.inicio:
            inicio = pd.Timestamp(args.inicio)
            fin = pd.Timestamp(args.fin) if args.fin else inicio + pd.Timedelta(days=2)
        else:
            campanas = postmortem.listar_campanas(cur)
            if campanas.empty:
                raise SystemExit("No hay campanas en WKND_PROMO_PLAN - sube un plan primero (run_estrategias.py).")
            inicio = pd.Timestamp(campanas.iloc[0]["CAMPAIGN_START"])
            fin = pd.Timestamp(campanas.iloc[0]["CAMPAIGN_END"])

        print(f"Campana: {inicio.date()} a {fin.date()} | origen={origen or 'todos'} | adopcion={adopcion or 'todas'}")

        if args.sin_refrescar:
            print("--sin-refrescar: usando la tabla materializada tal como esta.")
        else:
            print("Refrescando la tabla materializada (paga los joins pesados una sola vez)...")
            postmortem.crear_objetos_postmortem(cur)

        print("Midiendo...")
        resumen_mecanica = postmortem.performance_por_mecanica(cur, inicio, fin, origen=origen, adopcion=adopcion)
        total_planeado = postmortem.contar_plan(cur, inicio, fin)
        resumen_adopcion_df = postmortem.resumen_adopcion(cur, inicio, fin)
        top_skus_df = postmortem.top_skus(cur, inicio, fin, n=20, origen=origen, adopcion=adopcion)
        marketplace_df = postmortem.resumen_por_marketplace(cur, inicio, fin, origen=origen, adopcion=adopcion)
        segmento_usuario_df = postmortem.resumen_por_segmento_usuario(cur, inicio, fin, origen=origen, adopcion=adopcion)
        categoria_df = postmortem.resumen_por_categoria(resumen_mecanica)
        departamento_df = postmortem.resumen_por_departamento(resumen_mecanica)
        categoria_plataforma_df = postmortem.resumen_por_categoria_y_plataforma(cur, inicio, fin, origen=origen, adopcion=adopcion)
        departamento_plataforma_df = postmortem.resumen_por_departamento_y_plataforma(cur, inicio, fin, origen=origen, adopcion=adopcion)
        categoria_segmento_df = postmortem.resumen_por_categoria_y_segmento(cur, inicio, fin, origen=origen, adopcion=adopcion)
        departamento_segmento_df = postmortem.resumen_por_departamento_y_segmento(cur, inicio, fin, origen=origen, adopcion=adopcion)
        plataforma_segmento_df = postmortem.resumen_por_plataforma_y_segmento(cur, inicio, fin, origen=origen, adopcion=adopcion)
        usuarios_segmento_df = postmortem.resumen_usuarios_por_segmento(cur, inicio, fin, origen=origen, adopcion=adopcion)
        descuento_plataforma_segmento_df = postmortem.resumen_descuento_plataforma_segmento(
            cur, inicio, fin, origen=origen, adopcion=adopcion
        )
        enganche_df = postmortem.resumen_enganche_ticket(cur, inicio, fin)
        enganche_orden_df = postmortem.resumen_enganche_por_orden(cur, inicio, fin)
        enganche_segmento_df = postmortem.resumen_enganche_por_segmento(cur, inicio, fin)

        print("\n=== ADOPCION ===")
        print(f"Planeado: {total_planeado}")
        print(resumen_adopcion_df.to_string(index=False))

        print("\n=== PERFORMANCE POR MECANICA (top 15 por GMV) ===")
        print(resumen_mecanica.head(15).to_string(index=False))

        print("\n=== POR PLATAFORMA ===")
        print(marketplace_df.to_string(index=False))

        print("\n=== POR TIPO DE CLIENTE ===")
        print(segmento_usuario_df.to_string(index=False))

        print("\n=== USUARIOS DISTINTOS POR SEGMENTO ===")
        print(usuarios_segmento_df.to_string(index=False))

        print("\n=== ENGANCHE POR ORDEN (¿el carrito con promo fue mas grande?) ===")
        print(enganche_orden_df.to_string(index=False))

        print("\n=== ENGANCHE POR CLIENTE (gasto total en la ventana) ===")
        print(enganche_df.to_string(index=False))

        print("\n=== ENGANCHE POR TIPO DE CLIENTE (¿el reactivado que compro campaña, compro mas?) ===")
        print(enganche_segmento_df.to_string(index=False))

        ruta_reporte = postmortem.generar_reporte_html(
            resumen_mecanica, top_skus_df, inicio, fin,
            resumen_df=resumen_adopcion_df, total_planeado=total_planeado,
            marketplace_df=marketplace_df, segmento_usuario_df=segmento_usuario_df,
            categoria_df=categoria_df, departamento_df=departamento_df,
            categoria_plataforma_df=categoria_plataforma_df,
            departamento_plataforma_df=departamento_plataforma_df,
            categoria_segmento_df=categoria_segmento_df,
            departamento_segmento_df=departamento_segmento_df,
            plataforma_segmento_df=plataforma_segmento_df,
            usuarios_segmento_df=usuarios_segmento_df,
            descuento_plataforma_segmento_df=descuento_plataforma_segmento_df,
            enganche_df=enganche_df,
            enganche_orden_df=enganche_orden_df,
            enganche_segmento_df=enganche_segmento_df,
        )
        print(f"\nListo. Reporte HTML en: {ruta_reporte}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
