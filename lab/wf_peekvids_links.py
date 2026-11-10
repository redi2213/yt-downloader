"""Imported workflow tool (made by Lab > Add workflow). The workflow is .github/workflows/lab-peekvids-extract-links.yml on the lab branch."""
from labx import wf_runner

WORKFLOW = "lab-peekvids-extract-links.yml"
TITLE = "PeekVids \u2013 Extract links [imported]"


def build(host):
    wf_runner.build(host, WORKFLOW, TITLE)
