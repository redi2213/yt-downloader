"""Imported workflow tool (made by Lab > Add workflow). The workflow is .github/workflows/lab-fetch-file.yml on the lab branch."""
from labx import wf_runner

WORKFLOW = "lab-fetch-file.yml"
TITLE = "Fetch a file [imported]"


def build(host):
    wf_runner.build(host, WORKFLOW, TITLE)
