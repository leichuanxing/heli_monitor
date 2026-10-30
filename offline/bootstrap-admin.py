"""Read installer credentials from stdin; never persist or echo passwords."""
import json
import os
import re
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
sys.path.insert(0, "/app")
import django

django.setup()
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction


def main():
    values = json.load(sys.stdin)
    username, password = values["username"], values["password"]
    if not re.fullmatch(r"[A-Za-z0-9_.@+-]{1,150}", username):
        raise ValidationError("登录用户名格式无效")
    user_model = get_user_model()
    user = user_model(username=username, is_staff=True, is_superuser=True, is_active=True)
    validate_password(password, user)
    if sys.argv[1] == "create":
        with transaction.atomic():
            if user_model.objects.filter(username=username).exists():
                raise ValidationError("用户已存在，安装器不会覆盖已有账号密码")
            user.set_password(password)
            user.save()
        print("登录用户已创建：" + username)
    elif sys.argv[1] == "validate":
        print("登录账号与密码策略校验通过")
    else:
        raise ValidationError("无效的初始化模式")


if __name__ == "__main__":
    try:
        main()
    except ValidationError as exc:
        print("账号校验失败：" + "；".join(exc.messages), file=sys.stderr)
        sys.exit(1)
