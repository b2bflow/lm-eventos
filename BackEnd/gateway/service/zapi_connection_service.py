"""Conexão do número da LM na Z-API: status, QR Code para conectar e desconectar.

Usado em Configurações > Integrações & API (só admin): a equipe vê se o WhatsApp está conectado,
conecta escaneando o QR Code ali mesmo e desconecta sem abrir o painel da Z-API. Usa a mesma
instância do ZAPIClient (ZAPI_BASE_URL, ZAPI_INSTANCE_ID, ZAPI_INSTANCE_TOKEN, ZAPI_CLIENT_TOKEN).

Estados devolvidos em `state`:
- connected: WhatsApp conectado (phone/name vêm de /device).
- disconnected: sem sessão; com qr=True traz o QR Code (data URI) para escanear.
- unreachable: a Z-API não respondeu (rede, credencial errada, instância vencida).
- not_configured: faltam as variáveis da instância no servidor.
"""
import base64
import os

import requests

from utils.logger import logger

CONNECTED = "connected"
DISCONNECTED = "disconnected"
UNREACHABLE = "unreachable"
NOT_CONFIGURED = "not_configured"


class ZapiConnectionError(Exception):
    """A Z-API recusou ou não respondeu a uma ação (desconectar)."""


class ZapiConnectionService:
    TIMEOUT = 15

    def __init__(self):
        self._base_url = (os.getenv("ZAPI_BASE_URL") or "").rstrip("/")
        self._instance_id = os.getenv("ZAPI_INSTANCE_ID") or ""
        self._instance_token = os.getenv("ZAPI_INSTANCE_TOKEN") or ""
        self._client_token = os.getenv("ZAPI_CLIENT_TOKEN") or ""

    def is_configured(self) -> bool:
        return bool(self._base_url and self._instance_id and self._instance_token)

    def _url(self, path: str) -> str:
        return f"{self._base_url}/instances/{self._instance_id}/token/{self._instance_token}/{path}"

    def _headers(self) -> dict:
        headers = {"Accept": "application/json"}
        if self._client_token:
            headers["Client-Token"] = self._client_token
        return headers

    def _get(self, path: str) -> requests.Response:
        response = requests.get(self._url(path), headers=self._headers(), timeout=self.TIMEOUT)
        response.raise_for_status()
        return response

    def _get_json(self, path: str) -> dict | None:
        """JSON da rota, ou None se a Z-API não respondeu (o erro fica no log, sem o token)."""
        try:
            body = self._get(path).json()
            return body if isinstance(body, dict) else {}
        except Exception as e:
            logger.warning(f"[ZapiConnection] Falha em GET /{path}: {type(e).__name__}")
            return None

    def _fetch_qr_code(self) -> tuple[str | None, str | None, bool]:
        """(QR Code como data URI, erro, já conectou).

        A rota /qr-code/image já respondeu tanto JSON ({"value": "data:image/..."}, {"connected": true}
        ou {"challenge": ...} para número que pede verificação extra) quanto a imagem crua: trata todos.
        """
        try:
            response = self._get("qr-code/image")
        except Exception as e:
            logger.warning(f"[ZapiConnection] Falha ao buscar o QR Code: {type(e).__name__}")
            return None, "Não foi possível gerar o QR Code agora. Tente de novo em alguns segundos.", False

        content_type = response.headers.get("Content-Type", "")
        if "application/json" not in content_type:
            encoded = base64.b64encode(response.content).decode("ascii")
            return f"data:image/png;base64,{encoded}", None, False

        body = response.json() or {}
        if body.get("connected") is True:
            return None, None, True
        if body.get("challenge"):
            return None, "Este número pede uma verificação extra: conecte pelo painel da Z-API.", False
        value = (body.get("value") or "").strip()
        if not value:
            return None, "A Z-API não devolveu o QR Code. Tente de novo em alguns segundos.", False
        if not value.startswith("data:"):
            value = f"data:image/png;base64,{value}"
        return value, None, False

    def status(self, with_qr: bool = False) -> dict:
        snapshot = {
            "state": NOT_CONFIGURED,
            "connected": False,
            "smartphone_connected": None,
            "phone": None,
            "name": None,
            "qr_code": None,
            "error": None,
        }
        if not self.is_configured():
            snapshot["error"] = "A instância da Z-API não está configurada no servidor (ZAPI_INSTANCE_ID e ZAPI_INSTANCE_TOKEN)."
            return snapshot

        body = self._get_json("status")
        if body is None:
            snapshot["state"] = UNREACHABLE
            snapshot["error"] = "A Z-API não respondeu. Confira a internet do servidor e as credenciais da instância."
            return snapshot

        connected = body.get("connected") is True
        snapshot["smartphone_connected"] = body.get("smartphoneConnected")
        if not connected and with_qr:
            qr_code, error, already_connected = self._fetch_qr_code()
            connected = already_connected
            snapshot["qr_code"] = qr_code
            snapshot["error"] = error

        snapshot["state"] = CONNECTED if connected else DISCONNECTED
        snapshot["connected"] = connected
        if connected:
            snapshot["qr_code"] = None
            snapshot["error"] = None
            device = self._get_json("device") or {}
            snapshot["phone"] = device.get("phone") or None
            snapshot["name"] = device.get("name") or None
        return snapshot

    def disconnect(self) -> dict:
        """Encerra a sessão do WhatsApp na instância (o número sai de "Aparelhos conectados")."""
        if not self.is_configured():
            raise ZapiConnectionError("A instância da Z-API não está configurada no servidor.")
        try:
            body = self._get("disconnect").json()
        except Exception as e:
            logger.error(f"[ZapiConnection] Falha ao desconectar: {type(e).__name__}")
            raise ZapiConnectionError("A Z-API não respondeu ao pedido para desconectar. Tente de novo.") from e
        if isinstance(body, dict) and body.get("value") is False:
            raise ZapiConnectionError("A Z-API recusou o pedido para desconectar.")
        return self.status()
