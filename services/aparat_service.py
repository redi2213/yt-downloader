"""Aparat work done on the phone itself (no GitHub workflow involved):

  - list the videos of a playlist / channel, so the user can tick some
  - get the direct download links of chosen (or all) videos

The Aparat logic lives in scripts/aparat_core.py, shared with the GitHub
workflow, so the phone and the workflow always behave the same.
"""
from core.async_utils import run_in_background
from scripts import aparat_core as core


def start_list(link, limit, on_done):
    """on_done(res) from a background thread: {'ok': True, 'entries': [{uid,
    title}], 'info': {...}} or {'ok': False, 'error': str}."""
    run_in_background(_list_thread, link, limit, on_done)


def _list_thread(link, limit, on_done):
    try:
        entries, _name, info = core.list_entries(link, limit)
        if not entries:
            on_done({"ok": False, "error": "No videos found for this link"})
            return
        on_done({"ok": True, "entries": entries, "info": info})
    except Exception as e:
        on_done({"ok": False, "error": f"Error: {str(e)[:80]}"})


def start_links(link, quality, limit, ids, on_done):
    """ids: chosen video ids, or empty for everything the link gives.
    on_done(res): {'ok': True, 'links': [...], 'names': [...], 'nearest': n}
    or {'ok': False, 'error': str}."""
    run_in_background(_links_thread, link, quality, limit, ids, on_done)


def _links_thread(link, quality, limit, ids, on_done):
    try:
        if ids:
            ids, _name, info = core.resolve_selected(link, ids)
        else:
            ids, _name, info = core.resolve_simple(link, limit)
        if not ids:
            on_done({"ok": False, "error": "No videos found for this link"})
            return
        playlist = (info or {}).get("playlist_id")
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=8) as ex:
            videos = list(ex.map(lambda u: core.get_video(u, playlist), ids))

        links, names, nearest, failed = [], [], 0, 0
        for n, video in enumerate(videos, 1):
            if not video:
                failed += 1
                continue
            match, exact = core.pick_link(video["links"], quality)
            if not match:
                failed += 1
                continue
            if not exact:
                nearest += 1
            links.append(match["url"])
            names.append(f"{n:02d} - {core.clean_name(video['title'], 150)}")
        if not links:
            on_done({"ok": False, "error": "No downloadable links found"})
            return
        on_done({"ok": True, "links": links, "names": names,
                 "nearest": nearest, "failed": failed})
    except Exception as e:
        on_done({"ok": False, "error": f"Error: {str(e)[:80]}"})
