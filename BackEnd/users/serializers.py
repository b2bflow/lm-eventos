from rest_framework import exceptions, serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth import authenticate
from users.models import User


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Login por e-mail (padrão do painel em produção). `username` continua aceito."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"] = serializers.EmailField(write_only=True, required=False)
        self.fields["username"] = serializers.CharField(write_only=True, required=False)

    def validate(self, attrs):
        email = (attrs.get("email") or "").strip()
        username = (attrs.get("username") or "").strip()
        password = attrs.get("password")

        user = None
        if email:
            user = User.objects.filter(email__iexact=email).first()
        elif username:
            user = User.objects.filter(username=username).first()

        self.user = authenticate(username=user.username, password=password) if user else None
        if self.user is None:
            raise exceptions.AuthenticationFailed(self.error_messages["no_active_account"], "no_active_account")

        refresh = self.get_token(self.user)
        return {
            "refresh": str(refresh),
            "access": str(refresh.access_token),
            "username": self.user.username,
            "is_admin": self.user.is_staff,
            "role": 'admin' if self.user.is_staff else self.user.role,
        }


class UserDTO(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'password', 'first_name', 'email', 'is_staff', 'role']
        extra_kwargs = {'password': {'write_only': True}}
