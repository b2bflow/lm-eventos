"""Sobe o backend com dados de demonstração em memória (perfil nucleus.settings_demo).

Z-API e IA ficam desligadas: envios são só registrados no log. Login: erica@demo.local / demo1234 (admin)
e sdr@demo.local / demo1234.
"""
from datetime import datetime, timedelta

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from utils.logger import logger


def _disable_external_services():
    from gateway.adapters.zapi_adapter import ZAPIClient
    from events import tasks

    def log_only(name):
        def _send(self, *args, **kwargs):
            logger.info(f"[DEMO] Z-API desligada: {name} {str(kwargs or args)[:300]}")
            return True
        return _send

    for method in ("send_message", "send_message_with_button", "send_contact", "send_button_list"):
        setattr(ZAPIClient, method, log_only(method))
    if hasattr(ZAPIClient, "send_document"):
        ZAPIClient.send_document = log_only("send_document")

    def demo_send_message(self, phone, message, split=True):
        # Id falso, como o da Z-API: a mensagem do painel ganha a opção de apagar.
        import uuid
        logger.info(f"[DEMO] Z-API desligada: send_message {phone} {message[:300]!r}")
        self.last_sent_ids = [f"DEMO-{uuid.uuid4().hex[:12]}"]
        return True

    ZAPIClient.send_message = demo_send_message
    ZAPIClient.delete_message = log_only("delete_message")
    tasks.trigger_ai_agent_task.apply_async = lambda *a, **kw: logger.info("[DEMO] IA desligada")


def seed_users():
    from users.models.user_model import User
    # A tela de login entra por e-mail
    if not User.objects.filter(username="erica").exists():
        User.objects.create_user(username="erica", email="erica@demo.local", password="demo1234", first_name="Erica",
                                 is_staff=True)
    if not User.objects.filter(username="sdr").exists():
        User.objects.create_user(username="sdr", email="sdr@demo.local", password="demo1234", first_name="SDR")
    for username in ("erica", "sdr"):  # bancos de demo criados antes do login por e-mail
        User.objects.filter(username=username, email="").update(email=f"{username}@demo.local")


def seed_chat():
    from chat.models.conversation_model import ConversationModel
    from chat.models.message_model import MessageModel
    from crm.models.custumer_model import Customer

    if Customer.objects.count():
        return
    now = datetime.utcnow()
    for i in range(60):
        customer = Customer(name=f"Cliente Demo {i:02d}", phone=f"55629{i:08d}", new_service=False).save()
        conv = ConversationModel(customer=customer, tag="AGENTE" if i % 3 else "OPERADOR",
                                 needs_attention=(i % 7 == 0), updated_at=now - timedelta(minutes=i * 5)).save()
        count = 300 if i == 0 else 4
        for j in range(count):
            incoming = j % 2 == 0
            MessageModel(conversation=conv, customer=customer, role="user" if incoming else "assistant",
                         direction="INCOMING" if incoming else "OUTGOING", status="RECEIVED" if incoming else "SENT_TO_GATEWAY",
                         content=f"Mensagem {j} da conversa {i}",
                         created_at=now - timedelta(minutes=i * 5, seconds=(count - j) * 30)).save()
        conv.last_message_content = f"Mensagem {count - 1} da conversa {i}"
        conv.save()

    first = ConversationModel.objects.order_by("-updated_at").first()
    MessageModel(conversation=first, customer=first.customer, role="user", direction="INCOMING", status="RECEIVED",
                 message_type="image", media_url="https://placehold.co/600x400/png",
                 content="<image-url>https://placehold.co/600x400/png</image-url> Foto do local").save()


class Command(BaseCommand):
    help = "Sobe o servidor de demonstração com dados em memória (só com --settings=nucleus.settings_demo)."

    def add_arguments(self, parser):
        parser.add_argument("addrport", nargs="?", default="127.0.0.1:8000")

    def handle(self, *args, **options):
        if not settings.SETTINGS_MODULE.endswith("settings_demo"):
            raise CommandError("rundemo só roda com --settings=nucleus.settings_demo")
        _disable_external_services()
        call_command("migrate", verbosity=0)
        seed_users()
        seed_chat()
        from devtools import seeds
        seeds.run_all()
        self.stdout.write(self.style.SUCCESS("Demo pronta. Login: erica@demo.local / demo1234 (admin) ou sdr@demo.local / demo1234."))
        call_command("runserver", options["addrport"], use_reloader=False)
