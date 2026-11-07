"""Imported workflow tool (made by Lab > Add workflow). The workflow is .github/workflows/lab-upload-test-1-.yml on the lab branch."""
from labx import wf_runner

WORKFLOW = "lab-upload-test-1-.yml"
TITLE = "Upload test [imported]"


def build(host):
    wf_runner.build(host, WORKFLOW, TITLE)
