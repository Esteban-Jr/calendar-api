from rest_framework import permissions

class IsOwnerOrReadOnly(permissions.BasePermission):
    """
    Custom permission to only allow owners of an object to edit it.
    """

    def has_object_permission(self, request, view, obj):
        # Read permissions are allowed to any request,
        # so we'll always allow GET, HEAD or OPTIONS requests.
        if request.method in permissions.SAFE_METHODS:
            return True

        # Events imported from a calendar link can't be changed here: the
        # link is the source (CO/BE18).
        if getattr(obj, 'feed_id', None):
            self.message = 'Imported from a calendar link; change it at the source.'
            return False

        # Write permissions are only allowed to the owner of the event.
        return obj.owner == request.user