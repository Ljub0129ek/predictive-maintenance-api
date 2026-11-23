"""Simpel rate limiting: højst N kald pr. klient (IP-adresse) inden for et tidsvindue.

Beskytter mod at én klient oversvømmer API'et, fx med mange falske målinger
eller ved at gætte API-nøglen. Tællingen ligger i hukommelsen, hvilket er nok
til én container i denne MVP.
"""

import time
from collections import defaultdict, deque
from threading import Lock


class RateLimiter:
    def __init__(self, max_calls: int = 20, window_seconds: float = 60.0) -> None:
        self.max_calls = max_calls
        self.window_seconds = window_seconds
        self._calls: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def allow(self, client_id: str) -> bool:
        now = time.monotonic()
        with self._lock:
            calls = self._calls[client_id]
            while calls and now - calls[0] >= self.window_seconds:
                calls.popleft()  # Glem kald, der er ældre end vinduet
            if len(calls) >= self.max_calls:
                return False
            calls.append(now)
            return True
