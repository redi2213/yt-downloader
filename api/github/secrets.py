"""GitHub repository Secrets, written from the app.

The Arvan Cloud keys are stored as repository Secrets so only the workflows
can read them; the app can create and delete them but never read a value
back. GitHub wants each value encrypted with the repository's public key
(libsodium sealed box - see core/sealedbox.py).

Needs a token allowed to write Secrets: a classic token with the ``repo``
scope, or a GitHub App / fine-grained token with "Secrets: Read and write".
"""
from api.github import client
from core import sealedbox
from core.config import API_BASE


def list_secret_names() -> list:
    """Names (never values) of the repository's Actions secrets."""
    names, page = [], 1
    while True:
        r = client.get(f"{API_BASE}/actions/secrets", params={"per_page": 100, "page": page})
        batch = r.json().get("secrets", [])
        names += [s["name"] for s in batch]
        if len(batch) < 100:
            return names
        page += 1


def put_secret(name: str, value: str) -> None:
    """Creates or replaces one secret."""
    key = client.get(f"{API_BASE}/actions/secrets/public-key").json()
    encrypted = sealedbox.encrypt_secret(key["key"], value)
    client.request("PUT", f"{API_BASE}/actions/secrets/{name}",
                   json={"encrypted_value": encrypted, "key_id": key["key_id"]})


def delete_secret(name: str) -> None:
    """Deletes one secret; a secret that is already gone is fine."""
    r = client.get_allow_missing(f"{API_BASE}/actions/secrets/{name}")
    if r.status_code == 404:
        return
    client.delete(f"{API_BASE}/actions/secrets/{name}")
