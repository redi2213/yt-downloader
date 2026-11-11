"""Navigator part for the Arvan files (Release History > Arvan files, To Arvan). Mixed into
screens/navigator.py: Navigator(ArvanController). Keeps the screen state in ``_arvan_*``."""


class ArvanController:
    # -- the file list of the whole bucket ---------------------------------------
    def refresh_arvan_in_background(self):
        """Once per app start: reads the Arvan list quietly (nothing is shown) so Arvan files is
        already up to date when it is opened."""
        if getattr(self, "_arvan_bg_started", False):
            return
        self._arvan_bg_started = True
        from services import arvan_service
        arvan_service.start_background_refresh(
            on_complete=lambda res: self.schedule(lambda: self._after_arvan_background(res)))

    def _after_arvan_background(self, res):
        if not res.get("ok") or getattr(self, "_arvan_deleting", 0) or getattr(self, "_arvan_stale", False):
            return          # (an upload / delete is newer than this list)
        self._arvan_data = res["data"]

    def show_arvan_item_menu(self, obj):
        from screens import arvan as arvan_screen
        arvan_screen.build_item_menu(self, obj)

    def start_arvan_inline_delete(self, objs, on_done):
        """Deletes without leaving the list; ``on_done(res)`` runs on the main thread."""
        from services import arvan_service
        self._arvan_deleting = getattr(self, "_arvan_deleting", 0) + 1

        def finished(res):
            self._arvan_deleting -= 1
            if res.get("ok"):
                self._arvan_data = res["data"]
                self._arvan_stale = False
            on_done(res)

        arvan_service.start_delete(
            [o["key"] for o in objs], on_status=None,
            on_complete=lambda res: self.schedule(lambda: finished(res)))

    def show_arvan_files(self, refresh=False):
        from services import arvan_service
        self.remember(lambda: self.show_arvan_files(False))
        if getattr(self, "_arvan_stale", False):   # files were uploaded since the list was read
            refresh = True
        data = getattr(self, "_arvan_data", None)
        if data and not refresh:
            self._render_arvan()
            return
        self.show_working("Reading the Arvan files...\n(about 40 seconds the first time)", job=None)
        starter = arvan_service.start_refresh if refresh else arvan_service.start_open
        starter(on_status=self.set_status,
                on_complete=lambda res: self.schedule(lambda: self._after_arvan_load(res)))

    def _after_arvan_load(self, res, note=""):
        if not res.get("ok"):
            self.show_result(res.get("error", "Failed"))
            return
        self._arvan_data = res["data"]
        self._arvan_stale = False
        self._arvan_page = 0
        self._arvan_sel = set()
        self._arvan_note = note
        self._render_arvan()

    def _render_arvan(self):
        from screens import arvan as arvan_screen
        data = self._arvan_data
        keys = {o["key"] for o in arvan_screen.objects_of(data)}
        sel = getattr(self, "_arvan_sel", None) or set()
        self._arvan_sel = {k for k in sel if k in keys}
        arvan_screen.build_list(self, data, page=getattr(self, "_arvan_page", 0),
                                selected=self._arvan_sel, note=getattr(self, "_arvan_note", ""))

    def show_arvan_page(self, page):
        self._arvan_page = max(0, page)
        self._render_arvan()

    # -- delete / rename -------------------------------------------------------
    def show_arvan_delete_confirm(self, objs):
        from screens import arvan as arvan_screen
        arvan_screen.build_delete_confirm(self, objs)

    def start_arvan_delete(self, objs):
        from services import arvan_service
        self.show_working(f"Deleting {len(objs)} file(s) from Arvan...", job=None)
        arvan_service.start_delete(
            [o["key"] for o in objs], on_status=self.set_status,
            on_complete=lambda res: self.schedule(lambda: self._after_arvan_change(res, "delete")))

    def show_arvan_rename(self, obj):
        from screens import arvan as arvan_screen
        arvan_screen.build_rename(self, obj)

    def start_arvan_rename(self, obj, new_name):
        from services import arvan_service
        if not new_name or new_name == obj["key"].rsplit("/", 1)[-1]:
            self.show_arvan_files()
            return
        old = obj["key"]
        new_key = new_name if "/" in new_name else (old.rsplit("/", 1)[0] + "/" + new_name if "/" in old else new_name)
        self.show_working("Renaming on Arvan...", job=None)
        arvan_service.start_rename(
            old, new_key, on_status=self.set_status,
            on_complete=lambda res: self.schedule(lambda: self._after_arvan_change(res, "rename")))

    def _after_arvan_change(self, res, action):
        from services import arvan_service
        if not res.get("ok"):
            self.show_result(res.get("error", "Failed"))
            return
        self._after_arvan_load(res, note=arvan_service.action_summary(res["data"], action))

    # -- Release History -> To Arvan ---------------------------------------------
    def start_arvan_upload(self, items):
        from services import arvan_service
        self.show_working(f"Uploading {len(items)} file(s) to Arvan...\n(the files go from GitHub to Arvan)", job=None)
        arvan_service.start_upload(
            items, on_status=self.set_status,
            on_complete=lambda res: self.schedule(lambda: self._after_arvan_upload(res)))

    def _after_arvan_upload(self, res):
        if not res.get("ok"):
            self.show_result(res.get("error", "Failed"))
            return
        files = res["files"]
        self._arvan_stale = True   # the bucket changed: the next opening reads a fresh list
        text = f"Uploaded {len(files)} file(s) to Arvan"
        if res.get("warn"):
            text += "\n" + "\n".join(res["warn"])[:300]
        self.show_result(text, link=files[0]["url"], links=[f["url"] for f in files] if len(files) > 1 else None)
