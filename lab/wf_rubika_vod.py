"""Imported workflow tool (made by Lab > Add workflow). The workflow is .github/workflows/lab-rubika-vod.yml on the lab branch."""
from labx import wf_runner

WORKFLOW = "lab-rubika-vod.yml"
TITLE = "Rubika VOD links"


def build(host):
    wf_runner.build(host, WORKFLOW, TITLE)
