import os

import snowflake.connector
from dotenv import load_dotenv

load_dotenv()


def get_connection():
    return snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        authenticator="externalbrowser",
        warehouse=os.environ.get("SNOWFLAKE_WAREHOUSE") or None,
        database=os.environ.get("SNOWFLAKE_DATABASE") or None,
        schema=os.environ.get("SNOWFLAKE_SCHEMA") or None,
        role=os.environ.get("SNOWFLAKE_ROLE") or None,
    )
