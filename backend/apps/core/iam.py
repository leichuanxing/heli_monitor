from django.contrib.auth.models import User
from rest_framework.exceptions import ValidationError

from .permissions import VALID_PERMISSIONS, user_permissions

SYSTEM_ROLES = {"SUPER_ADMIN", "ADMIN", "OPERATOR"}


def role_permissions(role):
    if role.code in {"SUPER_ADMIN", "ADMIN"}:
        return set(VALID_PERMISSIONS)
    if role.code == "OPERATOR" and not role.permissions:
        return VALID_PERMISSIONS - {"iam.manage"}
    return {
        item
        for item in (role.permissions or [])
        if isinstance(item, str) and item in VALID_PERMISSIONS
    }


def guard_user(actor, target, attrs, deleting=False):
    if not actor:
        return
    if not User.objects.filter(pk=actor.pk, is_active=True).exists():
        raise ValidationError({"detail": "当前账号已停用"})
    if target:
        if target.pk == actor.pk and (deleting or attrs.get("is_active") is False):
            raise ValidationError({"detail": "不能删除或停用当前登录账号"})
        if target.is_superuser and not actor.is_superuser:
            raise ValidationError({"detail": "只有超级管理员可以管理超级管理员账号"})
        if (
            target.is_superuser
            and target.is_active
            and (deleting or attrs.get("is_active") is False)
        ):
            if (
                not User.objects.filter(is_superuser=True, is_active=True)
                .exclude(pk=target.pk)
                .exists()
            ):
                raise ValidationError({"detail": "不能删除或停用最后一个有效超级管理员"})
        if not actor.is_superuser and not set().union(
            *(role_permissions(role) for role in target.business_roles.filter(is_enabled=True))
        ) <= user_permissions(actor):
            raise ValidationError({"detail": "不能管理权限高于自身的账号"})
    if not actor.is_superuser:
        for role in attrs.get("business_roles", []):
            if role.code in SYSTEM_ROLES or not role_permissions(role) <= user_permissions(actor):
                raise ValidationError({"roles": "不能分配系统角色或超出自身权限的角色"})
    if target and target.pk == actor.pk and not actor.is_superuser and "business_roles" in attrs:
        effective = set().union(
            *(role_permissions(role) for role in attrs["business_roles"] if role.is_enabled)
        )
        if "iam.manage" in user_permissions(actor) and "iam.manage" not in effective:
            raise ValidationError({"roles": "不能移除自己的组织管理权限"})


def guard_role(actor, instance, attrs, deleting=False):
    if not actor:
        return
    if not User.objects.filter(pk=actor.pk, is_active=True).exists():
        raise ValidationError({"detail": "当前账号已停用"})
    code = attrs.get("code", getattr(instance, "code", ""))
    if instance and instance.code in SYSTEM_ROLES and code != instance.code:
        raise ValidationError({"code": "系统角色编码不能修改"})
    if not actor.is_superuser:
        if code in SYSTEM_ROLES or (instance and instance.code in SYSTEM_ROLES):
            raise ValidationError({"detail": "只有超级管理员可以管理系统角色"})
        own = user_permissions(actor)
        if instance and not role_permissions(instance) <= own:
            raise ValidationError({"detail": "不能管理权限高于自身的角色"})
        if not set(attrs.get("permissions", getattr(instance, "permissions", []))) <= own:
            raise ValidationError({"permissions": "不能授予超出自身范围的权限"})
    if (
        instance
        and instance.code in SYSTEM_ROLES
        and "permissions" in attrs
        and attrs["permissions"] != instance.permissions
    ):
        raise ValidationError({"permissions": "系统角色权限固定，请创建自定义角色配置权限"})
    if instance and instance.users.filter(pk=actor.pk).exists() and not actor.is_superuser:
        other = set().union(
            *(
                role_permissions(role)
                for role in actor.business_roles.filter(is_enabled=True).exclude(pk=instance.pk)
            )
        )
        proposed = (
            set(attrs.get("permissions", instance.permissions))
            if attrs.get("is_enabled", instance.is_enabled) and not deleting
            else set()
        )
        if "iam.manage" not in other | proposed:
            raise ValidationError({"detail": "不能移除自己最后一个组织管理角色的权限"})
