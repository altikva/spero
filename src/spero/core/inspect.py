# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-06
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (https://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: Fetch the YAML of the object a target supervises (k9s-style inspect).

"""Inspect a target's underlying object as YAML.

A target's probe declares what it watches via ``Probe.object_ref()``; this runs
``kubectl get <ref> -o yaml`` through the target's provider so `spero top` can show
the live object on demand. Host / data-infra targets have no single k8s object and
raise LookupError.
"""

from __future__ import annotations

from spero.core.models import TargetPolicy


async def object_yaml(target: TargetPolicy) -> str:
    """Return the target's object as YAML. Raises LookupError (no object) / RuntimeError."""
    from spero.probes import build_probe
    from spero.providers.host import make_provider

    ref = build_probe(target.probe).object_ref()
    if ref is None:
        raise LookupError(f"{target.name}: probe {target.probe.type!r} has no inspectable object")
    provider = make_provider(target.provider)
    r = await provider.run(["get", *ref, "-o", "yaml"], timeout=30)
    if not r.ok:
        raise RuntimeError(r.stderr.strip() or "kubectl get failed")
    return r.stdout
