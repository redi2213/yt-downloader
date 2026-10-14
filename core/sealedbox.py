"""libsodium-compatible "sealed box" encryption in pure Python.

GitHub only accepts a repository Secret encrypted with the repository's
public key using libsodium's ``crypto_box_seal``. PyNaCl does that, but it is
a C extension that is hard to build for Android, so this module implements the
same algorithm with the standard library only (the values encrypted here are
tiny - API keys - so speed does not matter):

    sealed = ephemeral_public_key || crypto_box(message, nonce, recipient_pk, ephemeral_sk)
    nonce  = blake2b(ephemeral_public_key || recipient_pk, digest_size=24)
    crypto_box = XSalsa20-Poly1305 keyed by HSalsa20(X25519(sk, pk), 0^16)

No Kivy and no network here. If PyNaCl happens to be installed it is used
instead (``seal`` tries it first).
"""
import base64
import hashlib
import os
import struct

_MASK32 = 0xFFFFFFFF
_P25519 = 2 ** 255 - 19
_A24 = 121665


# ---------------------------------------------------------------- X25519 ---
def _clamp(k: bytes) -> int:
    b = bytearray(k)
    b[0] &= 248
    b[31] &= 127
    b[31] |= 64
    return int.from_bytes(b, "little")


def x25519(scalar: bytes, u: bytes) -> bytes:
    """RFC 7748 X25519 (Montgomery ladder)."""
    k = _clamp(scalar)
    x1 = int.from_bytes(u, "little") & ((1 << 255) - 1)
    x2, z2, x3, z3, swap = 1, 0, x1, 1, 0
    p = _P25519
    for t in range(254, -1, -1):
        k_t = (k >> t) & 1
        swap ^= k_t
        if swap:
            x2, x3 = x3, x2
            z2, z3 = z3, z2
        swap = k_t
        a = (x2 + z2) % p
        aa = (a * a) % p
        b = (x2 - z2) % p
        bb = (b * b) % p
        e = (aa - bb) % p
        c = (x3 + z3) % p
        d = (x3 - z3) % p
        da = (d * a) % p
        cb = (c * b) % p
        x3 = pow(da + cb, 2, p)
        z3 = (x1 * pow(da - cb, 2, p)) % p
        x2 = (aa * bb) % p
        z2 = (e * (aa + _A24 * e)) % p
    if swap:
        x2, x3 = x3, x2
        z2, z3 = z3, z2
    return ((x2 * pow(z2, p - 2, p)) % p).to_bytes(32, "little")


_BASEPOINT = (9).to_bytes(32, "little")


def public_key(secret: bytes) -> bytes:
    return x25519(secret, _BASEPOINT)


# ---------------------------------------------------------------- Salsa20 ---
def _rotl(v, n):
    return ((v << n) & _MASK32) | (v >> (32 - n))


def _salsa_rounds(x):
    for _ in range(10):
        # column round
        x[4] ^= _rotl((x[0] + x[12]) & _MASK32, 7)
        x[8] ^= _rotl((x[4] + x[0]) & _MASK32, 9)
        x[12] ^= _rotl((x[8] + x[4]) & _MASK32, 13)
        x[0] ^= _rotl((x[12] + x[8]) & _MASK32, 18)
        x[9] ^= _rotl((x[5] + x[1]) & _MASK32, 7)
        x[13] ^= _rotl((x[9] + x[5]) & _MASK32, 9)
        x[1] ^= _rotl((x[13] + x[9]) & _MASK32, 13)
        x[5] ^= _rotl((x[1] + x[13]) & _MASK32, 18)
        x[14] ^= _rotl((x[10] + x[6]) & _MASK32, 7)
        x[2] ^= _rotl((x[14] + x[10]) & _MASK32, 9)
        x[6] ^= _rotl((x[2] + x[14]) & _MASK32, 13)
        x[10] ^= _rotl((x[6] + x[2]) & _MASK32, 18)
        x[3] ^= _rotl((x[15] + x[11]) & _MASK32, 7)
        x[7] ^= _rotl((x[3] + x[15]) & _MASK32, 9)
        x[11] ^= _rotl((x[7] + x[3]) & _MASK32, 13)
        x[15] ^= _rotl((x[11] + x[7]) & _MASK32, 18)
        # row round
        x[1] ^= _rotl((x[0] + x[3]) & _MASK32, 7)
        x[2] ^= _rotl((x[1] + x[0]) & _MASK32, 9)
        x[3] ^= _rotl((x[2] + x[1]) & _MASK32, 13)
        x[0] ^= _rotl((x[3] + x[2]) & _MASK32, 18)
        x[6] ^= _rotl((x[5] + x[4]) & _MASK32, 7)
        x[7] ^= _rotl((x[6] + x[5]) & _MASK32, 9)
        x[4] ^= _rotl((x[7] + x[6]) & _MASK32, 13)
        x[5] ^= _rotl((x[4] + x[7]) & _MASK32, 18)
        x[11] ^= _rotl((x[10] + x[9]) & _MASK32, 7)
        x[8] ^= _rotl((x[11] + x[10]) & _MASK32, 9)
        x[9] ^= _rotl((x[8] + x[11]) & _MASK32, 13)
        x[10] ^= _rotl((x[9] + x[8]) & _MASK32, 18)
        x[12] ^= _rotl((x[15] + x[14]) & _MASK32, 7)
        x[13] ^= _rotl((x[12] + x[15]) & _MASK32, 9)
        x[14] ^= _rotl((x[13] + x[12]) & _MASK32, 13)
        x[15] ^= _rotl((x[14] + x[13]) & _MASK32, 18)
    return x


_SIGMA = b"expand 32-byte k"


def _init_state(key: bytes, nonce16: bytes):
    c = struct.unpack("<4I", _SIGMA)
    k = struct.unpack("<8I", key)
    n = struct.unpack("<4I", nonce16)
    return [c[0], k[0], k[1], k[2], k[3], c[1], n[0], n[1],
            n[2], n[3], c[2], k[4], k[5], k[6], k[7], c[3]]


def _salsa20_block(key: bytes, nonce8: bytes, counter: int) -> bytes:
    n16 = nonce8 + struct.pack("<Q", counter)
    inp = _init_state(key, n16)
    x = _salsa_rounds(list(inp))
    return struct.pack("<16I", *[(x[i] + inp[i]) & _MASK32 for i in range(16)])


def hsalsa20(key: bytes, nonce16: bytes) -> bytes:
    x = _salsa_rounds(_init_state(key, nonce16))
    return struct.pack("<8I", x[0], x[5], x[10], x[15], x[6], x[7], x[8], x[9])


def _xsalsa20_stream(key: bytes, nonce24: bytes, length: int) -> bytes:
    subkey = hsalsa20(key, nonce24[:16])
    out = bytearray()
    counter = 0
    while len(out) < length:
        out += _salsa20_block(subkey, nonce24[16:], counter)
        counter += 1
    return bytes(out[:length])


# --------------------------------------------------------------- Poly1305 ---
def _poly1305(msg: bytes, key: bytes) -> bytes:
    r = int.from_bytes(key[:16], "little") & 0x0FFFFFFC0FFFFFFC0FFFFFFC0FFFFFFF
    s = int.from_bytes(key[16:32], "little")
    p = (1 << 130) - 5
    acc = 0
    for i in range(0, len(msg), 16):
        block = msg[i:i + 16]
        n = int.from_bytes(block + b"\x01", "little")
        acc = ((acc + n) * r) % p
    return ((acc + s) & ((1 << 128) - 1)).to_bytes(16, "little")


# ------------------------------------------------------------ box / seal ---
def secretbox(message: bytes, nonce24: bytes, key: bytes) -> bytes:
    stream = _xsalsa20_stream(key, nonce24, 32 + len(message))
    cipher = bytes(m ^ s for m, s in zip(message, stream[32:]))
    return _poly1305(cipher, stream[:32]) + cipher


def box(message: bytes, nonce24: bytes, their_pk: bytes, my_sk: bytes) -> bytes:
    shared = hsalsa20(x25519(my_sk, their_pk), bytes(16))
    return secretbox(message, nonce24, shared)


def _seal_pure(message: bytes, recipient_pk: bytes, ephemeral_sk: bytes = None) -> bytes:
    esk = ephemeral_sk if ephemeral_sk is not None else os.urandom(32)
    epk = public_key(esk)
    nonce = hashlib.blake2b(epk + recipient_pk, digest_size=24).digest()
    return epk + box(message, nonce, recipient_pk, esk)


def seal(message: bytes, recipient_pk: bytes) -> bytes:
    """crypto_box_seal(message, recipient_pk). Uses PyNaCl when present."""
    try:
        from nacl.public import PublicKey, SealedBox  # type: ignore
        return SealedBox(PublicKey(recipient_pk)).encrypt(message)
    except Exception:
        return _seal_pure(message, recipient_pk)


def encrypt_secret(public_key_b64: str, value: str) -> str:
    """What GitHub's "create or update a repository secret" call needs:
    the repo public key (base64) + the plain value -> base64 sealed box."""
    pk = base64.b64decode(public_key_b64)
    if len(pk) != 32:
        raise ValueError("Unexpected GitHub public key size")
    return base64.b64encode(seal(value.encode("utf-8"), pk)).decode("ascii")
