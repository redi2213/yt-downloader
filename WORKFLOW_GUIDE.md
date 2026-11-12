# How to write a GitHub Actions workflow for the YT Bridge app

> **To the AI assistant reading this:** a person gave you this guide together with a request ("make a tool that does X").
> Build a workflow that follows every rule below, so the YT Bridge app (an Android app that uses GitHub Actions as its
> backend) can start it, find its run, show the result and test it. The person imports your work with the app's
> **Lab > Add workflow** button (uploading the .yml, pasting it, or giving a link). The app checks it against these same
> rules and can fix some things by itself, but a workflow that follows the rules from the start needs no fixing.
> If something in the request is unclear in a way that changes the result (which site, what output, which secrets),
> ask ONE short question first. Otherwise just build it.

## 1. How the app uses a workflow

1. The app starts it by file name with `workflow_dispatch` and sends the inputs as strings. It always adds `job_id`
   (a unique id), `run_title` and `rerun`.
2. It finds its own run by looking for `job_id` inside the run name, then waits for the run to finish.
3. On success it lists the files of the GitHub Release tagged `run-<run id>`. The release is made by the repo's
   `scripts/storage_publish.py` (it also supports Arvan Cloud). No release means no file in the app.
4. On failure it shows the log and the `::error::` lines. A clear error line lets the person fix the problem.
5. New tools are tested in the Lab first: the real file lives on the `lab` branch and a tiny registration stub with the
   same name and inputs lives on `main`. You do not create the stub; the app does.

## 2. Rules (all of them are checked by the app)

1. **Triggers**: only `workflow_dispatch`. Never `push`, `schedule` or `pull_request` (they would also fire by themselves).
2. **Inputs**: every input is `type: string` (write booleans as the strings `'true'` / `'false'`).
   *Yes/no input*: end the `description` with `(true/false)` and use `default: 'true'` or `'false'`. *Fixed list*: write the
   options in the description, like `Protocol: http, socks4, socks5 or all`, with `default: 'all'`. The app then shows a
   popup list instead of a text box (no typing). Keep the default clean: `'50'`, never a hint like `'50 (Max)'`; the app
   shows the input name and its description above the box. Use `required: true`
   only when the tool cannot work without it; give every other input a `default`. Short, plain-English `description`
   (it becomes the label in the app). Input names are lowercase snake_case, and every `inputs.x` you use must be declared.
3. **Standard inputs, copy exactly** (keep them even if the tool does not use them): `job_id`, `run_title`, `rerun`,
   and, when you publish with `storage_publish.py`, also `storage` and `arvan_bucket`. See the template.
4. **run-name**, exactly this shape (replace `inputs.file_url` with the tool's main input):
   `run-name: ${{ inputs.run_title || inputs.file_url }} [${{ inputs.job_id }}]${{ inputs.rerun && format(' ~{0}', inputs.rerun) || '' }}`
5. **Permissions**: top-level `permissions: contents: write` (needed to make the release).
6. **Pass inputs through `env:`**, never put `${{ inputs.x }}` inside a `run:` command. In the script use `"$NAME"`.
   (Quoting problems and command injection otherwise.)
7. **Finished files go into the folder `out/`** (flat, no sub-folders). Do not leave temporary files there.
   File names must be readable and safe: no `/ \ : * ? " < > |`, no emoji (4-byte Unicode breaks GitHub asset labels).
   With yt-dlp use `--windows-filenames` (not `--restrict-filenames`, it strips non-ASCII letters).
8. **Publish with the repo's script**, exactly like the template: check out the scripts from `main`
   (`ref: main`, `path: _repo`, `sparse-checkout: scripts`) and run
   `python3 _repo/scripts/storage_publish.py publish --dir out --tag "run-${{ github.run_id }}" --title "<Tool> run-${{ github.run_id }}"`.
   The tag MUST be `run-${{ github.run_id }}`. Keep `ref: main`: the lab branch has no `scripts/` folder. Do not create the
   release yourself with `gh release create` or a release action unless the person asks for something special; if you do,
   the tag is still `run-${{ github.run_id }}`.
9. **Fail loudly**: when the real work fails, print one line `echo "::error::<what went wrong, in plain words>"` and
   `exit 1`. No `|| true` and no `continue-on-error` on the step that does the real work. Print what is being processed
   (never a secret) so the log tells the story.
10. **One job**, `runs-on: ubuntu-latest`, `timeout-minutes` set. Install everything you need explicitly
    (`python3 -m pip install ...`); do not assume a package exists. Pin actions by major version (`actions/checkout@v4`).
11. **Secrets**: only through `${{ secrets.NAME }}` into `env:`; never print them or write them where they can be published.
    If a step writes a secret to a file (cookies), delete it in a later step with `if: always()`. Name every secret you
    need in your answer (the person has to add it in the repo settings) and in the header (`# app-secrets:`).
12. **Self-contained when possible**: put short scripts inside the yml (`python3 - <<'PY'` ... `PY`). If a script is long,
    deliver it as a separate file under `lab_scripts/<app-id>/` and run it as `python3 lab_scripts/<app-id>/name.py`.
13. **Tool card** in the first lines of the file (comments the app reads to pre-fill the form):
    ```
    # app-id: file_fetch          (letters, digits, _ ; max 30)
    # app-title: Fetch a file     (the button's name)
    # app-group: upload           (optional)
    # app-domains: site.com, x.org   (optional: links from these sites are sent to this tool)
    # app-secrets: NAME1, NAME2   (optional)
    ```
14. **Notification step** (`Notify (ntfy)`, `if: always()`, `continue-on-error: true`) is optional but recommended; copy it
    from the template and only change `TOOL_NAME`.
15. Do not use `actions/upload-artifact` as the only output (the app reads releases, not artifacts), do not hard-code
    tokens or personal data, and do not add steps that need a self-hosted runner.

## 3. Good habits for the work itself

* Check the link / input first and fail early with a clear `::error::` message if it is wrong.
* Keep the log short and useful: progress lines are good, a thousand identical lines are not.
* Large files: a GitHub Release asset must be smaller than 2 GiB (the publish script falls back or reports it).
* yt-dlp tools: `python3 -m pip install -U yt-dlp` first; a mid-download 403 on heavy streams is often an expired signed
  URL, putting the `tv` player client first in `player_client` is the most stable; cookies (if needed) come from a secret.
* Network calls: add `--retry 3` / timeouts; never wait forever.

## 3b. Phone-friendly workflows (the app can also run them on the phone, with the phone's own IP)

Lab > the tool > **Run on this phone** runs the `RUN` steps inside the app and skips GitHub-only steps (checkout, publish,
Notify, anything with an `if:`). It works when:

* The real work is a Python script inside the yml: `python3 - <<'PY'` ... `PY`, with `python3` at the START of its line.
  Read inputs from `os.environ` (they arrive through `env:`). Do not capture its output with `$(python3 ...)`.
* Shell is only for small preparation (`mkdir`, `echo`, `grep`, `head`, `tr`, `export VAR`): the phone has a basic `sh`,
  no `curl`, `wget`, `jq`, `zip`, `git`, `ffmpeg`, `apt`, `sudo`, docker or node. Use Python (`urllib`, `requests`) for HTTP.
* Libraries must be pure Python (a `py3-none-any` wheel): `requests`, `beautifulsoup4`, `httpx`... The app downloads
  missing ones after showing their size. Native ones (numpy, lxml, pillow, cryptography) only run on GitHub.
* Do not run repo files (`python3 lab_scripts/x.py`) in the work step if you want the phone mode; inline the script.
* Results go to `out/`. Small text results (`.txt`, `.json`, `.csv`, up to 200 KB) are shown in the app with Copy
  buttons, so for lists write one item per line (for proxies: `IP:PORT | note`).
* Keep loops bounded (a time limit or a count): the phone has no 6-hour runner.

A workflow that needs a heavy tool is still welcome: just say "Runs on the phone: no (needs ffmpeg)".

## 4. What to answer with

1. The workflow as ONE code block (```yaml), complete, nothing elided, starting with the tool card comments.
2. Every extra file in its own code block, with its exact repo path as a heading (`### lab_scripts/file_fetch/x.py`).
   Say "no extra files" if there are none.
3. **Try it with**: two or three realistic example input sets (a value for every input the form asks for).
4. **Needs**: secrets, external services, known limits (one short line each). Say "nothing" if none.
5. **Phone**: one line, `Runs on the phone: yes` or `no (reason)`.
6. No long explanation. Do not wrap the workflow in a different format.

## 5. Self-check before you answer (answer only when every box is true)

- [ ] Only `workflow_dispatch`; every input `type: string`; every used `inputs.x` is declared.
- [ ] `job_id`, `run_title`, `rerun` declared (plus `storage`, `arvan_bucket` when publishing); `run-name` has `inputs.job_id`.
- [ ] `permissions: contents: write`; `timeout-minutes` set; no `${{ inputs.* }}` inside `run:` (only in `env:`).
- [ ] Files end up in `out/`; the publish step is the template's, with `ref: main` and the tag `run-${{ github.run_id }}`.
- [ ] A failing step prints `::error::...` and exits non-zero; secrets are never printed; temp secret files are removed.
- [ ] The YAML is valid (indentation with spaces, quotes closed, heredoc `PY` lines indented like the rest of the block).
- [ ] The tool card (`# app-id` ...) is on top; extra files are listed with their paths.
- [ ] Yes/no and fixed-list inputs are written as in rule 2 (`(true/false)`, options in the description); defaults carry no hints.
- [ ] Phone check: the work is inline Python reading `os.environ`, no curl/jq/ffmpeg in it, results in `out/`, loops bounded.

## 6. When the app reports a problem

The app's tool has a **Copy report** button: it puts the failed step, the probable causes, the log tail, the static checks
and the workflow file in one text. If the person pastes that to you, answer with the COMPLETE corrected workflow (and any
changed extra file), and say in two lines what was wrong. Do not answer with a diff.

## 7. Template (known to pass every check and to run)

This one downloads a file from a direct link and publishes it. Replace the "Download the file" step with the tool's real
work and change the names; keep everything else.

```yaml
# app-id: file_fetch
# app-title: Fetch a file from a link
# app-group: upload
# app-domains:
# app-secrets:
name: Fetch a file
run-name: ${{ inputs.run_title || inputs.file_url }} [${{ inputs.job_id }}]${{ inputs.rerun && format(' ~{0}', inputs.rerun) || '' }}

on:
  workflow_dispatch:
    inputs:
      file_url:
        description: 'Direct link of the file'
        required: true
        type: string
      job_id:
        description: 'Set by the app so it can find this exact run (leave empty when running by hand)'
        required: false
        default: ''
        type: string
      run_title:
        description: 'Short name for this run, set by the app (leave empty when running by hand)'
        required: false
        default: ''
        type: string
      rerun:
        description: 'Set by the app so Run again can repeat this run (leave empty when running by hand)'
        required: false
        default: ''
        type: string
      storage:
        description: 'Where to keep the file: github, arvan or both (set by the app)'
        required: false
        default: 'github'
        type: string
      arvan_bucket:
        description: 'Preferred Arvan bucket id (set by the app; empty = the main bucket)'
        required: false
        default: ''
        type: string

permissions:
  contents: write

jobs:
  run:
    runs-on: ubuntu-latest
    timeout-minutes: 60
    steps:
      - name: Download the file
        env:
          FILE_URL: ${{ inputs.file_url }}
        run: |
          set -euo pipefail
          mkdir -p out
          NAME=$(basename "${FILE_URL%%\?*}")
          [ -n "$NAME" ] || NAME="file_${GITHUB_RUN_ID}"
          if ! curl -fL --retry 3 --connect-timeout 20 -o "out/$NAME" "$FILE_URL"; then
            echo "::error::Could not download the link (is it a direct, public link?)"
            exit 1
          fi
          ls -la out

      - name: Get the publish scripts
        uses: actions/checkout@v4
        with:
          ref: main
          path: _repo
          sparse-checkout: scripts
      - name: Install boto3 (Arvan Cloud)
        if: ${{ (inputs.storage == 'arvan' || inputs.storage == 'both') }}
        run: python3 -m pip install --quiet boto3 || python3 -m pip install --quiet --break-system-packages boto3
      - name: Publish (GitHub Release and/or Arvan Cloud)
        env:
          GH_TOKEN: ${{ github.token }}
          STORAGE: ${{ inputs.storage || 'github' }}
          ARVAN_BUCKET: ${{ inputs.arvan_bucket }}
          ALL_SECRETS: ${{ (inputs.storage == 'arvan' || inputs.storage == 'both') && toJSON(secrets) || '' }}
        run: |
          python3 _repo/scripts/storage_publish.py publish --dir out --tag "run-${{ github.run_id }}" --title "Fetch run-${{ github.run_id }}"

      - name: Notify (ntfy)
        if: always()
        continue-on-error: true
        env:
          GH_TOKEN: ${{ github.token }}
          JOB_STATUS: ${{ job.status }}
          TOOL_NAME: Fetch a file
          RUN_TITLE: ${{ inputs.run_title }}
          RUN_URL: ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}
        run: |
          CFG=$(curl -fsS -m 20 -H "Authorization: Bearer $GH_TOKEN" \
            -H "Accept: application/vnd.github.raw+json" \
            "https://api.github.com/repos/$GITHUB_REPOSITORY/contents/ntfy.json?ref=config" 2>/dev/null || true)
          if [ -z "$CFG" ]; then echo "No ntfy.json on the config branch: no notification."; exit 0; fi
          RESULT=$(CFG="$CFG" python3 - <<'PY'
          import json, os, re
          try:
              d = json.loads(os.environ["CFG"])
          except Exception:
              d = {}
          topic = str(d.get("topic", "")).strip()
          server = str(d.get("server") or "https://ntfy.sh").strip().rstrip("/")
          if re.fullmatch(r"[A-Za-z0-9_-]{1,64}", topic) and re.fullmatch(r"https://[A-Za-z0-9.-]+(:[0-9]+)?", server):
              print(topic + " " + server)
          PY
          )
          if [ -z "$RESULT" ]; then echo "ntfy topic is not set: no notification."; exit 0; fi
          TOPIC=${RESULT%% *}
          SERVER=${RESULT#* }
          case "$JOB_STATUS" in
            success)   WORD="OK";        TAGS="white_check_mark"; PRIO="default" ;;
            cancelled) WORD="Cancelled"; TAGS="no_entry_sign";    PRIO="default" ;;
            *)         WORD="FAILED";    TAGS="x";                PRIO="high" ;;
          esac
          BODY="$TOOL_NAME: $WORD"
          if [ -n "${RUN_TITLE:-}" ]; then BODY="$BODY"$'\n'"$RUN_TITLE"; fi
          BODY="$BODY"$'\n'"$RUN_URL"
          if curl -fsS -m 20 -X POST "$SERVER/$TOPIC" -H "Title: YT Bridge - $TOOL_NAME - $WORD" \
              -H "Tags: $TAGS" -H "Priority: $PRIO" -H "Click: $RUN_URL" --data-binary "$BODY" >/dev/null; then
            echo "Notification sent."
          else
            echo "ntfy could not be reached."
          fi
```
