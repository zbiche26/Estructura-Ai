"""Identidad de proceso (hostname:pid) para diagnosticar colas compartidas.

Dos procesos reclamando la misma fila de message_jobs (p.ej. un worker
local corriendo en paralelo al de Railway) dejan el mismo rastro en BD
pero identidades de proceso distintas -- ver
spec/07-investigacion-mensajes-duplicados-2026-07-07.md.
"""

import os
import socket


def get_process_identity() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"
