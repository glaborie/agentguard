__all__ = ["app"]


def __getattr__(name: str):
    if name == "app":
        from app.api.app import app  # lazy — only loads fastapi when accessed
        return app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
