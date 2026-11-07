"""Imported workflow tool (made by Lab > Add workflow). The workflow is .github/workflows/lab-workflow.yml on the lab branch."""
from labx import wf_runner

WORKFLOW = "lab-workflow.yml"
TITLE = "Download Pinterest video [imported]"


def build(host):
    wf_runner.build(host, WORKFLOW, TITLE)
