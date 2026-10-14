"""Identidad de proceso (hostname:pid) usada para diagnosticar colisiones
de procesos reclamando la misma fila de message_jobs (ver
spec/07-investigacion-mensajes-duplicados-2026-07-07.md)."""

import os
import socket

from src.core.process_identity import get_process_identity


def test_get_process_identity_formato_host_pid():
    identity = get_process_identity()

    assert ":" in identity
    host, pid = identity.rsplit(":", 1)
    assert host == socket.gethostname()
    assert pid == str(os.getpid())
