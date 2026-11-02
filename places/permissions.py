from rest_framework.permissions import BasePermission, SAFE_METHODS


class StaffWriteOrReadOnly(BasePermission):
    def has_permission(self, request, view):
        return request.method in SAFE_METHODS or bool(request.user.is_authenticated and request.user.is_active and request.user.is_staff)
