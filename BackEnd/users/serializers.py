from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from users.models import User


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        email = attrs.get("email")
        password = attrs.get("password")

        try:
            user = User.objects.get(email=email)
            attrs["username"] = user.username
        except User.DoesNotExist:
            raise serializers.ValidationError("E-mail não encontrado")

        data = super().validate(attrs)
        data["username"] = self.user.username
        data["is_admin"] = self.user.is_staff
        return data


class UserDTO(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "password", "first_name", "email", "is_staff"]
        extra_kwargs = {"password": {"write_only": True}}
