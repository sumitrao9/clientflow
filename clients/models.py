"""The Client model is defined in ``accounts.models``.

It is registered in ``accounts/admin.py`` and served by ``clients.views.ClientViewSet``.
This module exists so the app has a conventional import location.
"""

from accounts.models import Client  # noqa: F401
