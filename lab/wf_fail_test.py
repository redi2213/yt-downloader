"""Imported workflow tool (made by Lab > Add workflow). The workflow is .github/workflows/lab-fail-test.yml on the lab branch."""
from labx import wf_runner

WORKFLOW = "lab-fail-test.yml"
TITLE = "Fail test [imported]"


def build(host):
    wf_runner.build(host, WORKFLOW, TITLE)
