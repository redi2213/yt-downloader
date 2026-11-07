"""Imported workflow tool (made by Lab > Add workflow). The workflow is .github/workflows/lab-file-fetch.yml on the lab branch."""
from labx import wf_runner

WORKFLOW = "lab-file-fetch.yml"
TITLE = "Fetch a file from a link [imported]"


def build(host):
    wf_runner.build(host, WORKFLOW, TITLE)
