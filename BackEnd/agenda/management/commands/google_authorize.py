"""Autoriza a conta do Google Agenda pelo terminal, sem o botão "Conectar Google" da plataforma.

Serve quando o endereço de retorno da plataforma não está cadastrado no client OAuth: usa um endereço
que já está lá (por padrão o primeiro de `redirect_uris` do client secret). Esse endereço pode nem abrir;
o que importa é o `code=` que o Google coloca na barra de endereço.

Uso (no console do Easypanel ou local):
    python manage.py google_authorize                      # mostra o link e pede o endereço de volta
    python manage.py google_authorize --code "<endereço>"  # troca direto
    python manage.py google_authorize --env-file .env      # grava também GOOGLE_REFRESH_TOKEN no arquivo

O refresh token é gravado no lm_settings (Mongo) e nunca é impresso.
"""
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from django.core.management.base import BaseCommand, CommandError

from agenda.services.google_calendar_client import GoogleCalendarClient, GoogleNotConfigured, _client_config, _client_section
from crm.models.lm_settings_model import LmSettings


def _code_from(value: str) -> str:
    value = value.strip()
    if "?" not in value and "=" not in value:
        return value
    query = parse_qs(urlparse(value).query)
    if query.get("error"):
        raise CommandError(f"O Google recusou a autorização: {query['error'][0]}")
    if not query.get("code"):
        raise CommandError("Não achei o code= no endereço colado.")
    return query["code"][0]


def _write_env(path: Path, token: str):
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    lines = [line for line in lines if not line.startswith("GOOGLE_REFRESH_TOKEN=")]
    lines.append(f"GOOGLE_REFRESH_TOKEN={token}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


class Command(BaseCommand):
    help = "Gera o link de autorização do Google Agenda e grava o refresh token a partir do code devolvido."

    def add_arguments(self, parser):
        parser.add_argument("--redirect-uri", help="Endereço de retorno cadastrado no client (padrão: o primeiro do client secret).")
        parser.add_argument("--code", help="O endereço completo para onde o Google redirecionou, ou só o code.")
        parser.add_argument("--env-file", help="Arquivo .env onde gravar GOOGLE_REFRESH_TOKEN (fora do git).")

    def handle(self, *args, **options):
        try:
            registered = _client_section(_client_config()).get("redirect_uris") or []
        except GoogleNotConfigured as e:
            raise CommandError(str(e))
        redirect = options["redirect_uri"] or (registered[0] if registered else None)
        if not redirect:
            raise CommandError("O client secret não lista nenhum endereço de retorno: use --redirect-uri.")
        client = GoogleCalendarClient()

        pasted = options["code"]
        if not pasted:
            self.stdout.write("1. Abra este link e entre com a conta do Google Agenda (Contato LM):\n")
            self.stdout.write(client.authorization_url(None, redirect=redirect) + "\n")
            self.stdout.write(f"2. Depois de permitir, o navegador vai para {redirect}?code=...")
            self.stdout.write("   A página pode dar erro de carregamento: tudo bem. Copie o endereço inteiro da barra.\n")
            pasted = input("3. Cole aqui o endereço: ")

        try:
            token = client.exchange_code(_code_from(pasted), None, redirect=redirect)
        except CommandError:
            raise
        except Exception as e:
            raise CommandError(f"Falha ao trocar o code (ele vale uma vez e por poucos minutos): {e}")

        cfg = LmSettings.get()
        cfg.google_refresh_token = token
        cfg.google_sync_token = ""
        cfg.save()
        self.stdout.write(self.style.SUCCESS("Autorizado: refresh token gravado no lm_settings."))
        if options["env_file"]:
            _write_env(Path(options["env_file"]), token)
            self.stdout.write(self.style.SUCCESS(f"GOOGLE_REFRESH_TOKEN gravado em {options['env_file']}."))
        self.stdout.write("Confira com: python manage.py check_google_calendar --roundtrip")
