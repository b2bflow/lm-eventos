import pytest
from chat.models.system_config_model import SystemConfig


@pytest.mark.django_db
def test_get_configuracoes_requires_admin(db):
    from rest_framework.test import APIClient
    from users.models.user_model import User
    user = User.objects.create_user(username="sdr", password="x")
    client = APIClient()
    client.force_authenticate(user=user)
    assert client.get("/api/v1/chat/configuracoes/").status_code == 403


@pytest.mark.django_db
def test_get_and_post_configuracoes_masks_secrets(api_client):
    SystemConfig(zapi_token="abcdef123456", zapi_instance_id="inst").save()

    resp = api_client.get("/api/v1/chat/configuracoes/")
    assert resp.status_code == 200
    assert resp.data["zapi_instance_id"] == "inst"
    assert resp.data["zapi_token"] == "••••3456"

    # Reenviar o valor mascarado não apaga o segredo real
    resp = api_client.post("/api/v1/chat/configuracoes/", {"zapi_token": "••••3456", "ai_active": False}, format="json")
    assert resp.status_code == 200
    config = SystemConfig.objects.first()
    assert config.zapi_token == "abcdef123456"
    assert config.ai_active is False
