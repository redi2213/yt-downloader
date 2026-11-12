"""Imported workflow tool (made by Lab > Add workflow). The workflow is .github/workflows/lab-site-suj-mobi.yml on the lab branch."""
from labx import wf_runner

WORKFLOW = "lab-site-suj-mobi.yml"
TITLE = "Lab Site Suj.mobi [imported]"


def build(host):
    wf_runner.build(host, WORKFLOW, TITLE)
