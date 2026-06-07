# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-07
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (https://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: Tests for the cert-expiry probe, using self-signed certs minted in-test.

"""Tests for spero.probes.kubernetes.CertExpiryProbe.

The cert generation needs cryptography, so the whole module is skipped when the
'certs' extra is not installed.
"""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta

import pytest

pytest.importorskip("cryptography")

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from spero.probes.kubernetes import CertExpiryProbe
from spero.providers.command import CommandResult


def _self_signed_pem(*, valid_for_days: int) -> bytes:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "spero.test")])
    now = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=valid_for_days))
        .sign(key, hashes.SHA256())
    )
    return cert.public_bytes(serialization.Encoding.PEM)


class _SecretProvider:
    def __init__(self, data: dict[str, str]) -> None:
        self._payload = json.dumps({"data": data})

    async def run(self, command: object, *, timeout: float | None = None) -> CommandResult:
        return CommandResult(0, self._payload, "")


def _secret(pem: bytes, *, key: str = "tls.crt") -> _SecretProvider:
    return _SecretProvider({key: base64.b64encode(pem).decode("ascii")})


async def test_long_lived_cert_is_healthy() -> None:
    provider = _secret(_self_signed_pem(valid_for_days=365))
    result = await CertExpiryProbe(secret="tls", days=14).check(provider)  # type: ignore[arg-type]
    assert result.healthy
    assert "until expiry" in result.detail


async def test_short_lived_cert_is_unhealthy() -> None:
    provider = _secret(_self_signed_pem(valid_for_days=3))
    result = await CertExpiryProbe(secret="tls", days=14).check(provider)  # type: ignore[arg-type]
    assert not result.healthy


async def test_expired_cert_is_unhealthy() -> None:
    provider = _secret(_self_signed_pem(valid_for_days=-1))
    result = await CertExpiryProbe(secret="tls", days=14).check(provider)  # type: ignore[arg-type]
    assert not result.healthy
    assert "expired" in result.detail


async def test_missing_key_is_unhealthy() -> None:
    provider = _secret(_self_signed_pem(valid_for_days=365), key="other.crt")
    result = await CertExpiryProbe(secret="tls", days=14).check(provider)  # type: ignore[arg-type]
    assert not result.healthy
    assert "tls.crt" in result.detail


async def test_custom_key_is_read() -> None:
    provider = _secret(_self_signed_pem(valid_for_days=365), key="ca.crt")
    result = await CertExpiryProbe(secret="tls", days=14, key="ca.crt").check(provider)  # type: ignore[arg-type]
    assert result.healthy


async def test_unparseable_cert_is_unhealthy() -> None:
    provider = _SecretProvider({"tls.crt": base64.b64encode(b"not a cert").decode("ascii")})
    result = await CertExpiryProbe(secret="tls").check(provider)  # type: ignore[arg-type]
    assert not result.healthy
    assert "could not parse certificate" in result.detail


def test_negative_days_rejected() -> None:
    with pytest.raises(ValueError, match="days must be >= 0"):
        CertExpiryProbe(secret="tls", days=-1)


def test_object_ref() -> None:
    assert CertExpiryProbe(secret="tls").object_ref() == ["secret", "tls"]


def test_build_from_spec() -> None:
    from spero.core.models import ProbeSpec
    from spero.probes import build_probe

    probe = build_probe(ProbeSpec(type="cert-expiry", params={"secret": "tls", "days": 30}))
    assert isinstance(probe, CertExpiryProbe)
    assert probe.days == 30
