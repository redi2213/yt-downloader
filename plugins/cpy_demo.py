WORKFLOW = "cpy-wf-v2.yml"


def build(host):
    host.title("v3")
    host.button("Run", lambda: host.gh.dispatch(WORKFLOW, {}))
    host.back_button("Back")
