import os
import oracledb

_INITIALIZED = False


def init_client():
    global _INITIALIZED
    if _INITIALIZED:
        return

    # Linux Thick mode: libraries must already be discoverable via LD_LIBRARY_PATH
    oracledb.init_oracle_client()
    _INITIALIZED = True


def get_connection():
    init_client()
    return oracledb.connect(
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        dsn=os.environ["DB_DSN"],
    )
