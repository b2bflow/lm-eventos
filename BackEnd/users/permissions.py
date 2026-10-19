"""Papéis da operação comercial e permissões DRF por papel.

admin: Erica (aprovações, ajuste manual, tudo). sdr: time comercial. porta: Lúcia (locação de
porta: contrato, retirada, cobrança). b2bflow: equipe da b2bflow. is_staff sempre conta como admin.
"""
from rest_framework.permissions import BasePermission

ADMIN = 'admin'
SDR = 'sdr'
PORTA = 'porta'
B2BFLOW = 'b2bflow'


def user_role(user) -> str | None:
    if not user or not getattr(user, 'is_authenticated', False):
        return None
    if user.is_staff or getattr(user, 'role', None) == ADMIN:
        return ADMIN
    return getattr(user, 'role', None) or SDR


def has_role(user, *roles: str) -> bool:
    role = user_role(user)
    return role == ADMIN or role in roles


def RolePermission(*roles: str):
    """Permissão DRF que libera admin e os papéis informados. Ex.: permission_classes = [RolePermission(PORTA)]."""

    class _RolePermission(BasePermission):
        message = 'Seu papel não permite esta ação.'

        def has_permission(self, request, view):
            return has_role(request.user, *roles)

    _RolePermission.__name__ = f"RolePermission_{'_'.join(roles) or 'admin'}"
    return _RolePermission


IsAdminRole = RolePermission()
