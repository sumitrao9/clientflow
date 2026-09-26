from rest_framework import permissions


class IsOwner(permissions.BasePermission):
    """Row-level ownership check.

    Every queryset in this project is already filtered to ``request.user``, so
    reaching a view is safe. This is the second line of defence: it blocks any
    object that was fetched by id without the owner filter (for example via a
    nested lookup), which is how cross-tenant IDOR bugs usually get in.
    """

    message = "You do not have access to this record."

    def has_object_permission(self, request, view, obj) -> bool:
        owner_id = getattr(obj, "owner_id", None)
        if owner_id is None:
            # Walk one level up for models that hang off a Client/Invoice.
            for attr in ("client", "invoice"):
                parent = getattr(obj, attr, None)
                if parent is not None:
                    owner_id = getattr(parent, "owner_id", None)
                    break
        return owner_id == request.user.id


class IsOwnerOrReadOnly(IsOwner, permissions.BasePermission):
    def has_object_permission(self, request, view, obj) -> bool:
        if request.method in permissions.SAFE_METHODS:
            return IsOwner.has_object_permission(self, request, view, obj)
        return IsOwner.has_object_permission(self, request, view, obj)
