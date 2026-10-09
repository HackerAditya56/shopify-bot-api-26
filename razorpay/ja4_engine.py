"""
ja4_engine.py — JA4 fingerprint diversity engine for WAF bypass.

Problem: curl_cffi's impersonation targets use static JA4 hashes that AWS WAF
Bot Control (Targeted) catalogues and rate-limits via RateLimitJA4Fingerprint.
tls_permute_extensions is NEUTRALIZED by JA4 — JA4 sorts extensions before
hashing, so extension order changes produce identical hashes.

Solution: Rotate through different curl_cffi impersonation targets (chrome124,
chrome131, chrome133a, chrome145) — all Chrome-on-Windows profiles that pass
Razorpay's WAF.  Each produces a fundamentally different JA4 hash because TLS
handshake parameters (ciphers, extensions, ALPN, PQ key shares) differ per
Chrome version.  Supplementary diversity via signature algorithm rotation +
GREASE + cert compression for intra-target variation.

Real JA4 diversity: 19 targets × 4 sig-alg sets × 2 cert compression
= ~152 unique JA4 hashes, all within Chrome's expected TLS parameter space.
Plus 7 primp targets = ~192 total across both backends.
(HTTP/2 parameters and GREASE do NOT contribute to JA4 — see estimated_diversity.)
"""

from __future__ import annotations

import os
import random
import hashlib
import time
from dataclasses import dataclass, field
from typing import Optional

# ── Impersonation Targets (each has a different JA4 hash) ────────────────────
# Chrome-only targets — Razorpay's AWS WAF only passes Chrome desktop/Android
# profiles.  Safari/Edge/Firefox impersonation gets 403'd (confirmed empirically).
# 19 Chrome versions (99–146) across Windows/macOS/Android platforms
# fingerprints across many more aggregation instances in AWS WAF's
# RateLimitJA4Fingerprint rule.

_IMPERSONATION_TARGETS: list[str] = [
    "chrome99",
    "chrome100",
    "chrome101",
    "chrome104",
    "chrome107",
    "chrome110",
    "chrome116",
    "chrome119",
    "chrome120",
    "chrome123",
    "chrome124",
    "chrome131",
    "chrome133a",
    "chrome136",
    "chrome142",
    "chrome145",
    "chrome146",
    "chrome99_android",
    "chrome131_android",
]

# ── TLS Signature Algorithm Sets ──────────────────────────────────────────────
# Rotating the set changes the signature_algorithms extension in ClientHello,
# which feeds directly into the JA4 extension+signature hash.  Each set is a
# valid real-browser ordering — no synthetic/random lists that would themselves
# be bot signals.

_SIG_ALG_SETS: list[list[str]] = [
    # Chrome 146 default ordering
    [
        "ecdsa_secp256r1_sha256", "rsa_pss_rsae_sha256", "rsa_pkcs1_sha256",
        "ecdsa_secp384r1_sha384", "rsa_pss_rsae_sha384", "rsa_pkcs1_sha384",
        "rsa_pss_rsae_sha512", "rsa_pkcs1_sha512", "rsa_pkcs1_sha1",
    ],
    # Chrome 131 variant (different ordering for RSA-PSS vs PKCS1)
    [
        "ecdsa_secp256r1_sha256", "rsa_pss_rsae_sha256", "rsa_pkcs1_sha256",
        "ecdsa_secp384r1_sha384", "rsa_pkcs1_sha384", "rsa_pss_rsae_sha384",
        "rsa_pss_rsae_sha512", "rsa_pkcs1_sha512", "rsa_pkcs1_sha1",
    ],
    # ECDSA-prioritized (Secure Hardware Chrome builds)
    [
        "ecdsa_secp256r1_sha256", "ecdsa_secp384r1_sha384",
        "rsa_pss_rsae_sha256", "rsa_pkcs1_sha256",
        "rsa_pss_rsae_sha384", "rsa_pkcs1_sha384",
        "rsa_pss_rsae_sha512", "rsa_pkcs1_sha512", "rsa_pkcs1_sha1",
    ],
    # PSS-preferred ordering (newer Linux Chrome builds)
    [
        "rsa_pss_rsae_sha256", "ecdsa_secp256r1_sha256", "rsa_pkcs1_sha256",
        "rsa_pss_rsae_sha384", "ecdsa_secp384r1_sha384", "rsa_pkcs1_sha384",
        "rsa_pss_rsae_sha512", "rsa_pkcs1_sha512", "rsa_pkcs1_sha1",
    ],
]


# ── JA4 Config ─────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class JA4Config:
    """A complete TLS fingerprint configuration for one checkout session.

    Each session gets a fresh config from the DiversityEngine.  The config
    specifies which impersonation target to use (determines JA4 hash) plus
    extra_fp parameters for intra-target variation.
    """
    # The curl_cffi impersonation target — the PRIMARY JA4 diversity mechanism
    impersonate_target: str = "chrome131"

    # Supplementary TLS variation (signature algorithms DO affect JA4)
    tls_grease: bool = True
    tls_cert_compression: str = "brotli"
    tls_signature_algorithms: Optional[list[str]] = None

    # HTTP/2 fingerprint variation
    http2_stream_weight: int = 256
    http2_stream_exclusive: int = 1

    # Metadata (not sent over the wire)
    config_id: str = ""
    diversity_seed: float = 0.0

    def to_dict(self) -> dict:
        """Return dict for curl_cffi extra_fp parameter."""
        d: dict = {
            "tls_grease": self.tls_grease,
            "tls_cert_compression": self.tls_cert_compression,
            "http2_stream_weight": self.http2_stream_weight,
            "http2_stream_exclusive": self.http2_stream_exclusive,
        }
        if self.tls_signature_algorithms is not None:
            d["tls_signature_algorithms"] = self.tls_signature_algorithms
        return d


# ── Diversity Engine ──────────────────────────────────────────────────────────

class DiversityEngine:
    """Generates unique JA4 fingerprint configs for each checkout session.

    Primary diversity: rotates through different curl_cffi impersonation targets
    (each has a fundamentally different JA4 hash).  Supplementary diversity:
    randomizes signature algorithms, GREASE, cert compression, and HTTP/2
    settings within each target.

    Usage:
        engine = DiversityEngine()
        config = engine.generate(attempt=0)   # first attempt — chrome124
        config = engine.generate(attempt=1)   # retry — chrome131 (different JA4)
        session = AsyncSession(
            impersonate=config.impersonate_target,
            extra_fp=config.to_dict(),
            ...
        )
    """

    def __init__(self, seed: int = None):
        self._rng = random.Random(seed)
        self._active_configs: set[str] = set()

    def generate(self, browser: str = "chrome", attempt: int = 0) -> JA4Config:
        """Generate a fresh JA4 fingerprint config.

        Args:
            browser: "chrome" or "firefox" — affects sig alg and target selection.
            attempt: 0-based retry attempt.  Each attempt uses a different
                     impersonation target to spread JA4 hashes across WAF
                     rate-limit aggregation instances.
        """
        # Primary diversity: rotate impersonation targets per attempt.
        # Each target has a completely different JA4 hash because TLS handshake
        # parameters (ciphers, extensions, ALPN, PQ key shares) differ per browser.
        #
        # PID offset: in Gunicorn pre-fork mode, 16 workers each have their own
        # DiversityEngine singleton.  Without this offset, all 16 start at the
        # same target (chrome124) and slam AWS WAF with identical JA4 hashes,
        # triggering RateLimitJA4Fingerprint → HTTP 403.  os.getpid() spreads
        # workers evenly across the 4 targets.
        pid_offset = os.getpid() % len(_IMPERSONATION_TARGETS)
        target_idx = (attempt + pid_offset) % len(_IMPERSONATION_TARGETS)
        impersonate_target = _IMPERSONATION_TARGETS[target_idx]

        # Supplementary diversity: intra-target TLS variation
        grease = self._rng.random() < 0.75
        compression = self._rng.choice(["brotli", "brotli", "zlib"])
        stream_weight = self._rng.randint(200, 256)
        stream_exclusive = self._rng.choice([1, 1, 1, 0])

        # Pick sig algs — these DO affect the JA4 extension hash
        if browser == "firefox":
            # Firefox uses a specific set — no Chrome variants
            sig_algs = [
                "ecdsa_secp256r1_sha256", "rsa_pss_rsae_sha256", "rsa_pkcs1_sha256",
                "ecdsa_secp384r1_sha384", "ecdsa_secp521r1_sha512",
                "rsa_pss_rsae_sha384", "rsa_pkcs1_sha384",
                "rsa_pss_rsae_sha512", "rsa_pkcs1_sha512", "rsa_pkcs1_sha1",
            ]
        else:
            sig_algs = self._rng.choice(_SIG_ALG_SETS)

        seed = self._rng.random()
        config_id = hashlib.md5(
            f"{impersonate_target}{grease}{compression}{stream_weight}"
            f"{stream_exclusive}{sig_algs}{seed}{time.time()}".encode()
        ).hexdigest()[:12]

        config = JA4Config(
            impersonate_target=impersonate_target,
            tls_grease=grease,
            tls_cert_compression=compression,
            tls_signature_algorithms=sig_algs,
            http2_stream_weight=stream_weight,
            http2_stream_exclusive=stream_exclusive,
            config_id=config_id,
            diversity_seed=seed,
        )
        self._active_configs.add(config_id)
        return config

    def release(self, config: JA4Config):
        """Mark a config as no longer in use (call after checkout completes)."""
        self._active_configs.discard(config.config_id)

    @property
    def active_count(self) -> int:
        return len(self._active_configs)

    @property
    def target_count(self) -> int:
        """Number of impersonation targets available for rotation."""
        return len(_IMPERSONATION_TARGETS)

    @property
    def targets(self) -> list[str]:
        """List of available impersonation targets."""
        return list(_IMPERSONATION_TARGETS)

    @property
    def estimated_diversity(self) -> int:
        """Realistic JA4 hash diversity estimate.

        Only counts TLS-layer parameters that affect JA4 hashing:
        - Impersonation targets (each has a fundamentally different JA4 hash)
        - Signature algorithm sets (affects JA4_c extension hash)
        - Cert compression (compress_certificate TLS extension 0x001B)

        HTTP/2 stream weight/exclusive are HTTP-layer SETTINGS, not TLS
        ClientHello — they contribute ZERO to JA4.  GREASE is stripped by
        JA4 before hashing JA4_b/JA4_c (only JA4_a count changes).

        Real diversity: targets × sig-alg sets × cert compression ≈ 80."""
        return (len(_IMPERSONATION_TARGETS) * len(_SIG_ALG_SETS) * 2)


# ── Module-level singleton ────────────────────────────────────────────────────

_engine: Optional[DiversityEngine] = None


def get_diversity_engine() -> DiversityEngine:
    """Get or create the module-level DiversityEngine singleton."""
    global _engine
    if _engine is None:
        _engine = DiversityEngine()
    return _engine


def generate_ja4_config(browser: str = "chrome", attempt: int = 0) -> JA4Config:
    """Convenience: generate a fresh JA4Config from the singleton engine."""
    return get_diversity_engine().generate(browser, attempt)


# ── CLI / Test ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    engine = DiversityEngine()
    print(f"Impersonation targets: {engine.targets}")
    print(f"Estimated diversity space: {engine.estimated_diversity} unique configurations\n")

    for i in range(6):
        c = engine.generate(attempt=i)
        print(f"[attempt {i}] id={c.config_id}  target={c.impersonate_target}")
        print(f"    grease={c.tls_grease}, compression={c.tls_cert_compression}")
        print(f"    h2_weight={c.http2_stream_weight}, h2_exclusive={c.http2_stream_exclusive}")
        sig_preview = c.tls_signature_algorithms
        if sig_preview:
            print(f"    sig_algs={sig_preview[0]}, {sig_preview[1]}, ...")
        print()
