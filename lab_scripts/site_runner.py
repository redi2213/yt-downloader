#!/usr/bin/env python3
"""Runs ONE site adapter (the one under test) through the same chain as Link Lab:
GitHub IP -> free proxies -> v2ray configs, then file sizes, xh_links.json / xh_links.txt and the
Job Summary. The adapter file calls run_adapter() from its own `if __name__ == "__main__"` block.
Nothing here is specific to a site."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import links  # noqa: E402


def run_adapter(mod) -> None:
    links.register_adapter(mod)   # first: it wins over a registered site with the same id
    asyncio.run(links.main())     # main() also loads the sites already registered
