from __future__ import annotations

_TRUSTSTORE_INJECTED = False


def inject_truststore_once() -> None:
    """Branche le magasin système une seule fois pour tous les clients HTTP Argos."""
    global _TRUSTSTORE_INJECTED
    if _TRUSTSTORE_INJECTED:
        return
    try:
        import truststore
    except ImportError:
        return
    truststore.inject_into_ssl()
    _TRUSTSTORE_INJECTED = True
