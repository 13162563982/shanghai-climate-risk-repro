"""SSL hardening shim for the packaged environment.

Why this exists
---------------
`import climada` -> `contextily` -> `geopy` -> `ssl.create_default_context()`
enumerates the Windows certificate store. On this machine that store can be in
a state that raises::

    ssl.SSLError: [ASN1: NOT_ENOUGH_DATA]

We therefore wrap ``ssl.SSLContext.load_default_certs`` so that a failure while
reading the Windows store is tolerated: the context keeps whatever roots it
already loaded, and the certifi bundle is added on top.

Certificate verification is NEVER disabled and no check is skipped: after this
shim the context still verifies against the certifi CA bundle.

This module is picked up automatically because ``env\\run.ps1`` sets
``PYTHONPATH`` to this directory, so CPython's ``site`` module imports it at
start-up.
"""

import ssl

_ORIGINAL_LOAD_DEFAULT_CERTS = ssl.SSLContext.load_default_certs
_PATCH_FLAG = "_v8_ssl_shim_installed"


def _safe_load_default_certs(self, purpose=ssl.Purpose.SERVER_AUTH):
    """load_default_certs() that survives a corrupt Windows cert store."""
    try:
        _ORIGINAL_LOAD_DEFAULT_CERTS(self, purpose)
    except Exception:  # noqa: BLE001 - deliberately broad: env-state dependent
        # Broken Windows store (e.g. intermittent ASN1 parse failure).
        # Swallow it; certifi below still supplies a usable trust store.
        pass
    try:
        import certifi

        self.load_verify_locations(cafile=certifi.where())
    except Exception:  # noqa: BLE001 - certifi optional
        pass


if not getattr(ssl.SSLContext, _PATCH_FLAG, False):
    ssl.SSLContext.load_default_certs = _safe_load_default_certs
    setattr(ssl.SSLContext, _PATCH_FLAG, True)
