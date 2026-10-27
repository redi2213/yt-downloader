import base64
import hashlib

import pytest

from core import sealedbox as sb


def test_x25519_rfc7748_vector():
    k = bytes.fromhex("a546e36bf0527c9d3b16154b82465edd62144c0ac1fc5a18506a2244ba449ac4")
    u = bytes.fromhex("e6db6867583030db3594c1a424b15f7c726624ec26b3353b10a903a6d0ab1c4c")
    assert sb.x25519(k, u).hex() == "c3da55379de9c6908e94ea4df28d084f32eccf03491c71f754b4075577a28552"


def test_public_key_rfc7748_alice():
    sk = bytes.fromhex("77076d0a7318a57d3c16c17251b26645df4c2f87ebc0992ab177fba51db92c2a")
    assert sb.public_key(sk).hex() == "8520f0098930a754748b7ddcb43ef75a0dbf3a0d26381af4eba4a98eaa9b4e6a"


def test_both_sides_get_the_same_secret():
    a, b = bytes(range(1, 33)), bytes(range(33, 65))
    assert sb.x25519(a, sb.public_key(b)) == sb.x25519(b, sb.public_key(a))


def test_sealed_box_can_be_opened_by_the_recipient():
    rsk = bytes(range(100, 132))
    rpk = sb.public_key(rsk)
    sealed = sb._seal_pure(b"my secret value", rpk)
    epk, boxed = sealed[:32], sealed[32:]
    nonce = hashlib.blake2b(epk + rpk, digest_size=24).digest()
    shared = sb.hsalsa20(sb.x25519(rsk, epk), bytes(16))
    tag, cipher = boxed[:16], boxed[16:]
    stream = sb._xsalsa20_stream(shared, nonce, 32 + len(cipher))
    assert sb._poly1305(cipher, stream[:32]) == tag
    assert bytes(c ^ s for c, s in zip(cipher, stream[32:])) == b"my secret value"


def test_libsodium_can_open_our_sealed_box():
    nacl_public = pytest.importorskip("nacl.public")
    rsk = bytes(range(100, 132))
    sealed = sb._seal_pure(b"hello github", sb.public_key(rsk))
    assert nacl_public.SealedBox(nacl_public.PrivateKey(rsk)).decrypt(sealed) == b"hello github"


def test_encrypt_secret_shape_and_bad_key():
    pk = base64.b64encode(sb.public_key(bytes(range(32)))).decode()
    assert len(base64.b64decode(sb.encrypt_secret(pk, "value"))) == 32 + 16 + 5
    with pytest.raises(ValueError):
        sb.encrypt_secret(base64.b64encode(b"short").decode(), "v")
