"""Dummy tool used to test Promote."""
WORKFLOW = "promote-test.yml"


def build(host):
    host.title("Hello promoted test")
    host.text(host.gh.read_file("lab_scripts/promote_test.py"))
    host.button("Run", lambda: host.gh.dispatch(WORKFLOW, {}))
    host.back_button("Back")
