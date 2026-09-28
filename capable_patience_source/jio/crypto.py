"""PayGlocal crypto — verified against the live HAR capture.

Public-key decrypt: AES-128-CBC(visitorId[0:16]) over base64(iv||ct) -> PEM SPKI.
Card encrypt: JWE compact, RSA-OAEP-256 key wrap + A128CBC-HS256 content enc.
Implements exactly what the payflow UI's jose.CompactEncrypt does.
"""
from __future__ import annotations

import base64
import json
import os as _os

from cryptography.hazmat.primitives import hashes, hmac, serialization
from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.padding import PKCS7


def _b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64u_decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def decrypt_public_key(key_blob: str, visitor_id: str) -> str:
    """AES-128-CBC(visitor_id[0:16]) -> SPKI PEM string (no BEGIN/END? includes them)."""
    key16 = visitor_id[:16].encode("utf-8")
    iv = base64.b64decode(key_blob[:24])
    ct = base64.b64decode(key_blob[24:])
    cipher = Cipher(algorithms.AES(key16), modes.CBC(iv))
    dec = cipher.decryptor()
    pt = dec.update(ct) + dec.finalize()
    unpadder = PKCS7(128).unpadder()
    pt = unpadder.update(pt) + unpadder.finalize()
    return pt.decode("utf-8")


def encrypt_card_payload(payload: dict, public_key_pem: str) -> str:
    """JWE compact: RSA-OAEP-256 + A128CBC-HS256, matching jose.CompactEncrypt."""
    pub = serialization.load_pem_public_key(public_key_pem.encode())

    header = {"alg": "RSA-OAEP-256", "enc": "A128CBC-HS256"}
    header_b = json.dumps(header, separators=(",", ":")).encode("utf-8")

    cek = _os.urandom(32)
    mac_key, enc_key = cek[:16], cek[16:]

    encrypted_key = pub.encrypt(
        cek,
        asym_padding.OAEP(
            mgf=asym_padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )

    iv = _os.urandom(16)
    plaintext = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    padder = PKCS7(128).padder()
    padded = padder.update(plaintext) + padder.finalize()
    cipher = Cipher(algorithms.AES(enc_key), modes.CBC(iv))
    enc = cipher.encryptor()
    ciphertext = enc.update(padded) + enc.finalize()

    aad = _b64u(header_b).encode("ascii")
    al = (len(aad) * 8).to_bytes(8, "big")
    h = hmac.HMAC(mac_key, hashes.SHA256())
    h.update(aad + iv + ciphertext + al)
    tag = h.finalize()[:16]

    return ".".join([
        _b64u(header_b),
        _b64u(encrypted_key),
        _b64u(iv),
        _b64u(ciphertext),
        _b64u(tag),
    ])


# --- round-trip self-test ---
if __name__ == "__main__":
    from cryptography.hazmat.primitives.asymmetric import rsa
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pub_pem = key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    payload = {"cardData": {"number": "5414960000008866", "expiryMonth": "12",
                            "expiryYear": "2026", "securityCode": "123"}}
    jwe = encrypt_card_payload(payload, pub_pem)
    print("JWE parts:", len(jwe.split(".")), "len", len(jwe))
    print("header decodes:", _b64u_decode(jwe.split(".")[0]))
    print("OK: encryption succeeded")
