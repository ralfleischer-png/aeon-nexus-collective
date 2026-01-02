from flask import request, redirect


class HTTPSEnforcer:
    """Middleware til at tvinge HTTPS i production"""

    def __init__(self, app=None):
        self.app = app
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        self.app = app
        app.before_request(self.redirect_to_https)

    def redirect_to_https(self):
        # Tillad HTTP i debug
        if self.app and self.app.debug:
            return None

        # Allerede HTTPS?
        if request.is_secure:
            return None

        if request.headers.get("X-Forwarded-Proto", "").lower() == "https":
            return None

        url = request.url.replace("http://", "https://", 1)
        return redirect(url, code=301)
