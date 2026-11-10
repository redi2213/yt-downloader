"""Imported workflow tool (made by Lab > Add workflow). The workflow is .github/workflows/lab-pornhub-search-scraper.yml on the lab branch."""
from labx import wf_runner

WORKFLOW = "lab-pornhub-search-scraper.yml"
TITLE = "Pornhub Search Scraper [imported]"


def build(host):
    wf_runner.build(host, WORKFLOW, TITLE)
