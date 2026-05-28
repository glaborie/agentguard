# Import the FastAPI application instance directly.
# Previously used a __getattr__ lazy-loader, but Python's package machinery
# sets app.api.app (the submodule) as the 'app' attribute on the package
# before __getattr__ is ever called, causing uvicorn to receive a module
# object instead of the FastAPI instance.
from app.api.app import app  # noqa: F401  (re-exported for `uvicorn app.api:app`)

__all__ = ["app"]
