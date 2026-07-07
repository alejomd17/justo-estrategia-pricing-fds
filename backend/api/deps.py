from fastapi import Request


def get_cursor(request: Request):
    """Cursor nuevo por request sobre la conexion persistente compartida
    (app.state.conn) - abrir un cursor no re-autentica, es barato."""
    cur = request.app.state.conn.cursor()
    try:
        yield cur
    finally:
        cur.close()
