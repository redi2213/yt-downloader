class BaseScreen:
    def __init__(self, app):
        self.app = app

    def clear(self):
        self.app.clear_content()

    def add(self, widget):
        self.app.add(widget)
