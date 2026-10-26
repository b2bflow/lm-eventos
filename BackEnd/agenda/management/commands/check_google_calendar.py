"""Confere a conexão com o Google Agenda (conta Contato LM) sem expor credenciais.

Uso:
    python manage.py check_google_calendar               # agenda conectada e próximos eventos
    python manage.py check_google_calendar --create-test # cria e apaga um evento de teste com Meet
    python manage.py check_google_calendar --roundtrip   # ciclo completo pela plataforma (ver abaixo)

--roundtrip cria um bloqueio de teste pela plataforma, confere no Google, edita, sincroniza o espelho,
cancela e confere de novo. Só toca no evento que ele mesmo criou; os demais eventos são apenas lidos.
"""
from datetime import datetime, timedelta

from django.core.management.base import BaseCommand, CommandError

from agenda.models import CalendarEvent
from agenda.services.google_calendar_client import (
    GoogleCalendarClient, GoogleNotConfigured, _client_config, _client_section, parse_google_datetime, refresh_token,
)
from crm.services.business_hours import to_local, to_utc_naive

TEST_TITLE = "TESTE integração LM (pode apagar)"


class Command(BaseCommand):
    help = "Verifica o client secret, o refresh token e o acesso de leitura e escrita ao Google Agenda."

    def add_arguments(self, parser):
        parser.add_argument("--create-test", action="store_true",
                            help="Cria e remove um evento de teste com link do Meet (valida escrita).")
        parser.add_argument("--roundtrip", action="store_true",
                            help="Cria, edita e cancela um bloqueio de teste pela plataforma, conferindo o Google e o espelho.")

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

        if options["roundtrip"]:
            self._roundtrip(client)

    def _roundtrip(self, client: GoogleCalendarClient):
        from agenda.services.agenda_service import AgendaService

        service = AgendaService(google=client)
        self.stdout.write("Espelho: sincronizando Google -> plataforma (só leitura no Google)...")
        self.stdout.write(f"  {service.sync_from_google()}")

        # Fim de noite daqui a 2 dias: fora do horário comercial, não atrapalha a agenda real.
        day = (to_local(datetime.utcnow()) + timedelta(days=2)).date()
        start = to_utc_naive(datetime(day.year, day.month, day.day, 22, 0))
        event = service.schedule("bloqueio", start, start + timedelta(minutes=30), title=TEST_TITLE,
                                 notes="Criado pelo check_google_calendar --roundtrip.", notify_customer=False)
        google_id = event.get("google_event_id")
        try:
            if not google_id:
                raise CommandError(f"Evento não chegou ao Google: {event.get('sync_error') or event.get('warnings')}")
            self._expect(client.get_event(google_id), TEST_TITLE, start, "1. Criado pela plataforma e conferido no Google")

            new_start, new_title = start + timedelta(minutes=30), f"{TEST_TITLE} - editado"
            edited = service.update(event["id"], start=new_start, end=new_start + timedelta(minutes=30), title=new_title,
                                    notify_customer=False)
            if edited["sync_status"] != "sincronizado":
                raise CommandError(f"Edição não chegou ao Google: {edited.get('sync_error') or edited.get('warnings')}")
            self._expect(client.get_event(google_id), new_title, new_start, "2. Editado pela plataforma e conferido no Google")

            service.sync_from_google()
            mirror = CalendarEvent.objects(google_event_id=google_id)
            if mirror.count() != 1 or mirror.first().title != new_title or mirror.first().start != new_start:
                raise CommandError("Espelho divergente após sincronizar (duplicado ou desatualizado).")
            self.stdout.write(self.style.SUCCESS("3. Espelho sincronizado sem duplicar"))

            service.cancel(event["id"])
            if not self._gone(client, google_id):
                raise CommandError("4. Cancelado na plataforma, mas o evento continua no Google.")
            google_id = None  # já removido; o finally não precisa apagar
            service.sync_from_google()
            if CalendarEvent.objects(id=event["id"]).first().status != "cancelado":
                raise CommandError("Evento cancelado na plataforma continua ativo no espelho.")
            self.stdout.write(self.style.SUCCESS("4. Cancelado pela plataforma e removido do Google"))
        finally:
            if google_id:
                try:
                    client.delete_event(google_id)
                    self.stdout.write(self.style.WARNING("Teste interrompido: evento de teste removido do Google."))
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"Não consegui remover o evento de teste ({TEST_TITLE}): {e}"))
            CalendarEvent.objects(id=event["id"]).delete()
        self.stdout.write(self.style.SUCCESS("Ida e volta OK: criar, editar, espelhar e cancelar funcionando."))

    @staticmethod
    def _gone(client: GoogleCalendarClient, google_id: str) -> bool:
        try:
            return client.get_event(google_id).get("status") == "cancelled"
        except Exception as e:  # 404/410: já não existe
            return getattr(getattr(e, "resp", None), "status", None) in (404, 410)

    def _expect(self, item: dict, title: str, start: datetime, label: str):
        if item.get("status") == "cancelled" or item.get("summary") != title or parse_google_datetime(item["start"]) != start:
            raise CommandError(f"{label}: falhou (Google tem '{item.get('summary')}' em {item.get('start')}).")
        self.stdout.write(self.style.SUCCESS(label))
