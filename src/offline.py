"""Offline helpers.

Argos Translate uses Stanza as its sentence boundary detector. By default
Stanza checks GitHub for an updated ``resources.json`` on every start, which
breaks the "works with the network disconnected" requirement.

:func:`patch_stanza_offline` makes Stanza reuse the model files that are
already shipped inside the installed Argos package.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_patched = False


def patch_stanza_offline() -> bool:
    """Make Stanza reuse the bundled resources instead of downloading them.

    Returns True when the patch was applied.
    """
    global _patched
    if _patched:
        return True
    try:
        import stanza
        from stanza.pipeline.core import DownloadMethod
    except Exception:  # pragma: no cover - stanza is optional
        return False

    original_pipeline = stanza.Pipeline

    def offline_pipeline(*args: Any, **kwargs: Any):
        """Stanza pipeline that never downloads anything."""
        kwargs.setdefault("download_method", DownloadMethod.REUSE_RESOURCES)
        kwargs.setdefault("logging_level", "WARNING")
        return original_pipeline(*args, **kwargs)

    stanza.Pipeline = offline_pipeline
    _patched = True
    logger.debug("Stanza patched to work offline.")
    return True
