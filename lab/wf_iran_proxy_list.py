"""Imported workflow tool (made by Lab > Add workflow). The workflow is .github/workflows/lab-free-iran-proxy-list.yml on the lab branch."""
from labx import wf_runner

WORKFLOW = "lab-free-iran-proxy-list.yml"
TITLE = "Free Iran Proxy List [imported]"


def build(host):
    wf_runner.build(host, WORKFLOW, TITLE)
