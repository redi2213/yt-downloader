# Guide for the AI: write a Link Lab site adapter (and its test workflow)

You are helping the user add ONE website to the Link Lab of his Android app (YT Bridge, tab Lab).
The sites Link Lab does not support yet are added by an "adapter": a small Python file that reads the
site (usually its API) and returns the quality links of a video page. You write TWO files:

1. `SITE_ID.py`        the adapter (replace SITE_ID with a short lowercase name, e.g. `mysite`)
2. `lab-site-SITE_ID.yml`  the test workflow (a copy of the template below, only the names change)

The user sends you the API / page details of the site. If something you need is missing (an example
video link, the API address, a header), ask ONE short question first; otherwise write both files at once.
Answer in the user's language; the code and comments stay in English.

## How Link Lab uses the adapter
For a link of the site Link Lab calls `extract(url, proxy)`: first without a proxy (the GitHub IP), then with
every free proxy, then with the v2ray configs (the same chain as every other site; you do NOT write any of
that). When `extract` returns an error, yt-dlp is tried as a fallback. On the user's PHONE the same
`extract(url, None)` runs inside the app with the phone's own network (fast test, no proxy).

## The adapter file (rules)
```python
"""MySite adapter for Link Lab: <one line: what API it uses>."""
SITE_ID = "mysite"            # lowercase letters, digits, _ (same as the file name)
TITLE = "My Site"             # shown in the app
DOMAINS = ["mysite.com"]      # every domain of the site (subdomains match automatically)


def extract(url, proxy=None):
    """url: the video page. proxy: None, or 'socks5://host:port' / 'http://host:port'.
    Returns {"title": str, "qualities": [{"quality": "1080p", "link": "https://...", "ext": "mp4"}, ...]}
    or {"error": "short reason"} (never raise on purpose, never print secrets)."""
    import requests
    proxies = None
    if proxy:
        p = proxy.replace("socks5://", "socks5h://", 1)      # let the proxy resolve the name
        proxies = {"http": p, "https": p}
    headers = {"User-Agent": "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/124 Mobile Safari/537.36",
               "Referer": url}
    r = requests.get("https://api.mysite.com/video?id=...", headers=headers, proxies=proxies, timeout=20)
    r.raise_for_status()
    data = r.json()
    return {"title": data["title"],
            "qualities": [{"quality": "%sp" % q["h"], "link": q["url"], "ext": "mp4"} for q in data["files"]]}


if __name__ == "__main__":            # keep this block EXACTLY as it is: the test workflow runs this file
    import os, sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    import site_runner
    site_runner.run_adapter(sys.modules[__name__])
```
Rules:
- Plain synchronous Python. Use only the standard library and `requests` (and `yt_dlp` if you really need
  it). The app has nothing else, so an adapter that imports another package works only on GitHub, not on
  the phone: avoid that; if it is unavoidable say so clearly and add `pip install <package>` to the
  workflow's "Install Python deps" step.
- Every request has `timeout=` (at most 20 s). Pass `proxies=proxies` to EVERY request (that is how the
  proxy chain works). Do not use global proxy settings.
- Each quality: `quality` like "1080p" (the height with a `p`), `link` = a direct file link or an HLS
  (`.m3u8`) media playlist for that quality (not a master playlist that holds all qualities), `ext` = "mp4"
  or "m3u8". Several links of the same quality are fine. The best first is not required (Link Lab sorts).
- The download step later sends the video page URL as the Referer. If the file link needs other headers,
  say it in a comment at the top of the file and tell the user.
- No secrets in the code. If the API needs a key the user did not give, ask for it.
- `matches(url)` is optional (only if the domain check is not enough). `DOMAINS` is always required.

## The test workflow
Copy this file as `lab-site-SITE_ID.yml` and replace `SITE_ID` (4 places) and `SITE_TITLE` (1 place).
Change nothing else; it runs the same chain as Link Lab and publishes the links the app reads.
```yaml
name: Lab Site SITE_TITLE

# Link Lab test for ONE site adapter (lab_scripts/sites_pending/SITE_ID.py).
# Same chain as Link Lab: GitHub IP first, then the free proxies, then the v2ray configs.
# The links are written into the notes of release "run-<id>" so the app can show them.

run-name: ${{ inputs.run_title || 'Lab site SITE_ID' }} [${{ inputs.job_id }}]${{ inputs.rerun && format(' ~{0}', inputs.rerun) || '' }}

on:
  workflow_dispatch:
    inputs:
      job_id:
        description: 'Unique id the app puts in the run name to find this run (set by the app)'
        required: false
        default: ''
        type: string
      run_title:
        description: 'Short name for this run, set by the app (leave empty when running by hand)'
        required: false
        default: ''
        type: string
      rerun:
        description: 'Set by the app: the other inputs packed into the run name so "Run again" can repeat this run (leave empty when running by hand)'
        required: false
        default: ''
        type: string
      url:
        description: "Video page URL of the site (several links: one per line)"
        required: false
        type: string
      proxy:
        description: "Optional single proxy override (socks5://... or http://...)"
        required: false
        type: string
      v2ray_config:
        description: "Xray/V2Ray config (optional)"
        required: false
        type: string

permissions:
  contents: write

jobs:
  extract:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v4

      - name: Checkout lab branch (proxy list)
        uses: actions/checkout@v4
        continue-on-error: true
        with:
          ref: lab
          path: labcfg

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install Python deps
        timeout-minutes: 8
        run: |
          set -e
          pip install -U pip setuptools wheel
          pip install requests PySocks curl_cffi yt-dlp
          # add "pip install <package>" here ONLY if the adapter imports another package
          # (then the adapter cannot run on the phone, only on GitHub)

      - name: Setup Xray from config (optional)
        env:
          V2RAY_CONFIG: ${{ inputs.v2ray_config }}
        run: python3 lab_scripts/xray_setup.py || true

      - name: Default configs (auto-refreshed list; skipped when you set a proxy or config)
        if: ${{ inputs.v2ray_config == '' && inputs.proxy == '' }}
        run: python3 lab_scripts/xray_default.py || true

      - name: Prepare proxy list
        env:
          PROXY_IN: ${{ inputs.proxy }}
        run: |
          if [ -f labcfg/lab/working_proxies.txt ]; then
            cp labcfg/lab/working_proxies.txt working_proxies.txt
          fi
          if [ -n "$PROXY_IN" ]; then
            echo "$PROXY_IN" > working_proxies.txt
          fi
          echo "=== working_proxies.txt ==="
          cat working_proxies.txt 2>/dev/null || echo "(none)"

      - name: Extract quality links with the adapter
        env:
          URL: ${{ inputs.url }}
          PROXY: ${{ inputs.proxy }}
          V2RAY_CONFIG: ${{ inputs.v2ray_config }}
        run: python lab_scripts/sites_pending/SITE_ID.py

      - name: Publish the links as release notes (the app reads them)
        if: always() && hashFiles('xh_links.txt') != ''
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          TAG="run-${{ github.run_id }}"
          { echo "Lab site SITE_ID"; echo; cat xh_links.txt; } > lab_release_notes.md
          gh release delete "$TAG" --yes --repo "$GITHUB_REPOSITORY" 2>/dev/null || true
          gh release create "$TAG" --repo "$GITHUB_REPOSITORY" --prerelease \
            --title "Lab site SITE_ID #${{ github.run_number }}" \
            --notes-file lab_release_notes.md
```

## What to give the user
1. The two files, complete, each in its own code block with its file name above it.
2. These steps, short: Lab > "Add workflow" > pick BOTH files > Add (the adapter file is placed in
   `lab_scripts/sites_pending/`). Then open the new tool and test it with a link of the site: "Run" (GitHub:
   GitHub IP, proxies, configs) or "Run on this phone" (fast, this phone's network).
3. When it works: Lab > Add workflow > "Add a tested site to Link Lab". The site is then supported by Link
   Lab itself (Get links, Download, and the phone check).
4. If it fails he copies the report of the run ("Copy report") and sends it to you: fix the adapter and send
   the whole file again (same name).
