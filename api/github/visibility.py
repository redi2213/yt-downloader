"""Make the repository public or private (GitHub REST API).

Needs a token with admin rights on the repo (classic token: ``repo`` scope and
admin on the repo; fine-grained: "Administration: Read and write").
Pure API layer - no UI and no Kivy.
"""
from api.github import client
from core.config import API_BASE


def is_private() -> bool:
    """True when the repository is private right now."""
    return bool(client.get(API_BASE).json().get("private"))


def set_private(private: bool) -> bool:
    """Make the repository private (True) or public (False); returns the new state."""
    r = client.patch(API_BASE, json={"private": bool(private)})
    return bool(r.json().get("private"))
