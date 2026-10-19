"""Confere a conexão com o Google Agenda (conta Contato LM) sem expor credenciais.

Uso:
    python manage.py check_google_calendar               # agenda conectada e próximos eventos
    python manage.py check_google_calendar --create-test # cria e apaga um evento de teste com Meet
"""
from datetime import datetime, timedelta

from django.core.management.base import BaseCommand, CommandError

from agenda.services.google_calendar_client import (
    GoogleCalendarClient, GoogleNotConfigured, _client_config, _client_section, refresh_token,
)


class Command(BaseCommand):
    help = "Verifica o client secret, o refresh token e o acesso de leitura e escrita ao Google Agenda."

    def add_arguments(self, parser):
        parser.add_argument("--create-test", action="store_true",
                            help="Cria e remove um evento de teste com link do Meet (valida escrita).")

    def handle(self, *args, **options):
        try:
            section = _client_section(_client_config())
        except GoogleNotConfigured as e:
            raise CommandError(str(e))
        client_id = section.get("client_id", "")
        self.stdout.write(f"Client OAuth: ...{client_id[-30:]}")
        if not refresh_token():
            raise CommandError("Refresh token ausente: defina GOOGLE_REFRESH_TOKEN ou conecte pela página Agenda.")

        client = GoogleCalendarClient()
        try:
            info = client.calendar_info()
        except Exception as e:
            raise CommandError(
                f"Falha ao acessar o Google: {e}\n"
                "Verifique se o token foi emitido pelo MESMO client OAuth do client secret configurado "
                "e se a autorização incluiu o escopo do Google Agenda."
            )
        self.stdout.write(self.style.SUCCESS(f"Conectado à agenda: {info['summary']} ({info['id']}), fuso {info['time_zone']}"))

        events, _ = client.list_events(time_min=datetime.utcnow())
        upcoming = [e for e in events if e.get("status") != "cancelled"][:5]
        self.stdout.write(f"Próximos eventos lidos: {len(upcoming)}")
        for event in upcoming:
            start = event.get("start", {})
            self.stdout.write(f"  - {start.get('dateTime') or start.get('date')}  {event.get('summary', '(sem título)')}")

        if options["create_test"]:
            start = datetime.utcnow() + timedelta(days=1)
            created = client.create_event("Teste de integração OmniFlow (pode apagar)", start, start + timedelta(minutes=15),
                                          description="Evento criado e apagado pelo check_google_calendar.", with_meet=True)
            link = created.get("hangoutLink")
            client.delete_event(created["id"])
            if link:
                self.stdout.write(self.style.SUCCESS(f"Escrita OK: evento criado com Meet ({link}) e removido."))
            else:
                self.stdout.write(self.style.WARNING("Evento criado e removido, mas sem link do Meet: confira se a conta permite Google Meet."))
