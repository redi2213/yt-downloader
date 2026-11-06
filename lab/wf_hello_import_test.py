"""Imported workflow tool (made by Lab > Add workflow). The workflow is .github/workflows/lab-hello-import-test.yml on the lab branch."""
from labx import wf_runner

WORKFLOW = "lab-hello-import-test.yml"
TITLE = "Hello import test [imported]"


def build(host):
    wf_runner.build(host, WORKFLOW, TITLE)
