from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth import authenticate
from users.models import User


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"] = serializers.EmailField(write_only=True)
        del self.fields["username"]

    def validate(self, attrs):

        email = attrs.get("email")
        password = attrs.get("password")

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise serializers.ValidationError(
                self.default_error_messages,
                code="no_active_account",
            )

        self.user = authenticate(username=user.username, password=password)

        if self.user is None:
            raise serializers.ValidationError(
                self.default_error_messages,
                code="no_active_account",
            )

        refresh = self.get_token(self.user)

        data = {
            "refresh": str(refresh),
            "access": str(refresh.access_token),
        }
        data["username"] = self.user.username
        data["is_admin"] = self.user.is_staff
        return data


class UserDTO(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "password", "first_name", "email", "is_staff"]
        extra_kwargs = {"password": {"write_only": True}}
