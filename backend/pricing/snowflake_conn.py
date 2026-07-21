import os

import snowflake.connector
from dotenv import load_dotenv

load_dotenv()


def get_connection():
    """Conexion SSO interactiva (abre navegador) - usada por el notebook,
    los scripts run_*.py y el backend FastAPI.

    client_store_temporary_credential=True cachea el ID token del SSO en
    disco local (~/.cache/snowflake/): el navegador se abre UNA vez y las
    siguientes conexiones (otro script, reinicio de uvicorn, otro kernel)
    reusan el token hasta que expira, sin volver a pedir login. Requiere
    que la cuenta de Snowflake tenga ALLOW_ID_TOKEN habilitado - si no lo
    tiene, el conector simplemente vuelve a abrir el navegador (no falla).

    Para procesos 100% desatendidos (Docker/cron/Render, sin navegador ni
    la primera vez) esto no alcanza: se necesita key-pair, que sigue
    bloqueado por permisos (MODIFY PROGRAMMATIC AUTHENTICATION METHODS).
    """
    return snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        authenticator="externalbrowser",
        client_store_temporary_credential=True,
        warehouse=os.environ.get("SNOWFLAKE_WAREHOUSE") or None,
        database=os.environ.get("SNOWFLAKE_DATABASE") or None,
        schema=os.environ.get("SNOWFLAKE_SCHEMA") or None,
        role=os.environ.get("SNOWFLAKE_ROLE") or None,
    )
