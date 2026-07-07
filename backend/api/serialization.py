import json
from decimal import Decimal

import pandas as pd


def df_to_records(df: pd.DataFrame) -> list[dict]:
    """DataFrame -> list[dict] serializable por FastAPI. pd.to_json ya sabe
    resolver numpy int64/float64, NaN->null y fechas; json.loads solo lo
    decodifica de vuelta para que FastAPI lo envuelva en su propia
    respuesta.

    Snowflake devuelve columnas NUMERIC (ej. AVG(MARGIN)) como
    decimal.Decimal - pandas no los serializa como numero JSON nativo y
    caen como string (rompe .toFixed() del lado del frontend), asi que se
    convierten a float antes de exportar.
    """
    df = df.map(lambda v: float(v) if isinstance(v, Decimal) else v)
    return json.loads(df.to_json(orient="records", date_format="iso"))
