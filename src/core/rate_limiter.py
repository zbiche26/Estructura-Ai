"""Rate limiting utilidades para controlar mensajes por usuario."""
import time
import threading
from collections import deque
from typing import Deque, Dict, Optional, Tuple

class RateLimiter:
    """Rate limiter simple por usuario usando ventanas deslizantes."""

    def __init__(self, per_minute: int = 10, per_hour: int = 100):
        self.per_minute = per_minute
        self.per_hour = per_hour
        self._events: Dict[str, Deque[float]] = {}
        self._lock = threading.Lock()

    def _key(self, tenant_slug: str, user_id: str) -> str:
        return f"{tenant_slug}:{user_id}"

    def check(self, tenant_slug: str, user_id: str) -> Tuple[bool, Optional[str]]:
        """Revisa y registra un mensaje. Devuelve (permitido, mensaje_limite)."""
        now = time.time()
        key = self._key(tenant_slug, user_id)

        with self._lock:
            dq = self._events.setdefault(key, deque())
            
            # Limpiar eventos más antiguos de una hora (3600 segundos)
            while dq and now - dq[0] > 3600:
                dq.popleft()

            # Contar eventos en el último minuto (60 segundos)
            last_minute_count = 0
            minute_threshold = now - 60
            for ts in reversed(dq):
                if ts >= minute_threshold:
                    last_minute_count += 1
                else:
                    break
            if last_minute_count >= self.per_minute:
                return False, "🚦 Has enviado demasiados mensajes este minuto. Espera unos segundos."

            # Verificar el límite por hora
            if len(dq) >= self.per_hour:
                return False, "🚦 Alcanzaste el límite por hora. Intenta nuevamente más tarde."

            # Si pasa los chequeos, registrar el nuevo evento
            dq.append(now)
            return True, None

rate_limiter = RateLimiter()