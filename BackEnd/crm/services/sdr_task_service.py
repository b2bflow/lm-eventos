from datetime import datetime, timedelta

from bson import ObjectId

from crm.models.custumer_model import Customer
from crm.models.lm_settings_model import LmSettings
from crm.models.log_service_model import ServiceLog
from crm.models.sdr_task_model import CADENCE_TASKS, TASK_TYPES, SdrTask
from crm.repositories.log_service_repository import ServiceLogRepository
from crm import domain
from crm.services.business_hours import business_slot, first_call_due, to_local, to_utc_naive
from utils.logger import logger


class SdrTaskService:
    """Fila da SDR. Contato marcado como operador humano nunca recebe tarefa."""

    def create_task(self, customer_id: str, task_type: str, due_at: datetime, metadata: dict | None = None,
                    unique_pending: bool = True) -> SdrTask | None:
        if task_type not in TASK_TYPES:
            raise ValueError(f"Tipo de tarefa inválido: {task_type}")
        customer = Customer.objects(id=ObjectId(customer_id)).first()
        if not customer:
            raise ValueError("Lead não encontrado.")
        if customer.human_operator:
            logger.info(f"[SdrTask] {customer.phone} é operador humano: tarefa {task_type} não criada.")
            return None
        if unique_pending:
            existing = SdrTask.objects(customer=customer, type=task_type, status='pending').first()
            if existing:
                return existing
        task = SdrTask(customer=customer, type=task_type, due_at=due_at, metadata=metadata or {}).save()
        ServiceLogRepository.create_log(
            customer=customer, operator_id=None, action_type='TASK_CREATED',
            description=f"Tarefa criada: {TASK_TYPES[task_type]}.",
            metadata={"task_id": str(task.id), "type": task_type, "due_at": due_at.isoformat()},
        )
        return task

    def complete(self, task_id: str, user=None) -> SdrTask:
        task = SdrTask.objects(id=ObjectId(task_id)).first() if ObjectId.is_valid(task_id) else None
        if not task:
            raise ValueError("Tarefa não encontrada.")
        if task.status == 'pending':
            task.status = 'done'
            task.done_at = datetime.utcnow()
            task.done_by = str(user.id) if user and getattr(user, 'id', None) else None
            task.save()
            ServiceLogRepository.create_log(
                customer=task.customer, operator_id=task.done_by, action_type='TASK_DONE',
                description=f"Tarefa concluída: {TASK_TYPES.get(task.type, task.type)}.",
                metadata={"task_id": str(task.id), "type": task.type},
            )
        return task

    def complete_pending(self, customer_id: str, task_types: list[str], user=None) -> int:
        tasks = SdrTask.objects(customer=customer_id, type__in=task_types, status='pending')
        count = 0
        for task in tasks:
            self.complete(str(task.id), user=user)
            count += 1
        return count

    def cancel_pending_for_customer(self, customer_id: str) -> int:
        return SdrTask.objects(customer=customer_id, status='pending').update(set__status='canceled')

    def cancel_cadence(self, customer_id: str, types: tuple[str, ...] = CADENCE_TASKS) -> int:
        """Cancela as tarefas pendentes da cadência da proposta (lead saiu de PROPOSAL_SENT ou
        recebeu uma nova versão)."""
        return SdrTask.objects(customer=customer_id, type__in=list(types), status='pending').update(set__status='canceled')

    def list_tasks(self, status: str = 'pending', customer_id: str | None = None, limit: int = 100,
                   due_before: datetime | None = None) -> list[dict]:
        queryset = SdrTask.objects(status=status)
        if customer_id:
            queryset = queryset.filter(customer=customer_id)
        else:
            # Fila da SDR: só leads do funil (os antigos ficaram de fora quando o funil foi zerado)
            queryset = queryset.filter(customer__in=list(Customer.objects(funnel_entered_at__ne=None).scalar('id')))
        if due_before:
            queryset = queryset.filter(due_at__lt=due_before)
        return [t.to_dict() for t in queryset.order_by('due_at').limit(limit)]

    # --- Regras periódicas (Celery beat) ---------------------------------------------------

    def create_stale_lead_tasks(self, now: datetime | None = None) -> int:
        """Lead em NEW_LEAD sem mensagem do cliente há N horas (padrão 24) vira `retomar_lead_parado`."""
        from chat.models.message_model import MessageModel

        now = now or datetime.utcnow()
        cutoff = now - timedelta(hours=LmSettings.get().stale_lead_hours)
        created = 0
        candidates = Customer.objects(
            customer_state_now__in=[domain.NEW_LEAD, 'ANALYSIS'], human_operator__ne=True,
            contact_type__in=['lead', None], created_at__lte=cutoff, funnel_entered_at__ne=None,
        )
        for customer in candidates:
            last_incoming = MessageModel.objects(customer=customer, direction='INCOMING').order_by('-created_at').first()
            last_at = last_incoming.created_at if last_incoming else customer.created_at
            if last_at and last_at > cutoff:
                continue
            if SdrTask.objects(customer=customer, type='retomar_lead_parado', status='pending').first():
                continue
            # Uma tarefa por período parado: não recria se já houve uma depois da última mensagem.
            if SdrTask.objects(customer=customer, type='retomar_lead_parado', created_at__gte=last_at).first():
                continue
            self.create_task(str(customer.id), 'retomar_lead_parado', due_at=now,
                             metadata={"last_customer_message_at": last_at.isoformat() if last_at else None})
            created += 1
        return created

    # --- Cadência da proposta (follow-up D+1, D+3, D+5 e perda automática em D+7) --------------

    @staticmethod
    def _cycle_key(customer: Customer) -> str:
        """Cada envio de proposta abre um ciclo; as tarefas guardam o ciclo para não repetir."""
        return customer.proposal_sent_at.isoformat()

    @staticmethod
    def customer_responded_since(customer: Customer, since: datetime) -> bool:
        """Cliente deu sinal depois do envio: mensagem no WhatsApp, ligação atendida, reunião ou
        visita marcada, ou lead esperando a Erica (não é falta de resposta do cliente)."""
        from chat.models.message_model import MessageModel

        if set(customer.flags or []) & {'reuniao_agendada', 'visita_agendada', 'aguardando_erica'}:
            return True
        if MessageModel.objects(customer=customer, direction='INCOMING', created_at__gt=since).first():
            return True
        return bool(ServiceLog.objects(customer=customer, action_type='CALL_LOGGED', created_at__gt=since,
                                       metadata__outcome='atendeu').first())

    def run_proposal_cadence(self, now: datetime | None = None) -> dict:
        """Roda pelo Celery beat. Para cada lead em PROPOSAL_SENT:
        - cria a tarefa de follow-up do dia (D+1 ligação, D+3 WhatsApp, D+5 ligação), às 9h do dia
          ou no próximo horário útil; se o beat ficou parado, cria só a etapa mais recente e
          cancela as anteriores que ainda estiverem pendentes;
        - em D+7 sem resposta do cliente, move para Perdido ("sem resposta") e agenda a
          reativação em 30 dias.
        Dias corridos, contados no horário de Brasília."""
        now = now or datetime.utcnow()
        cfg = LmSettings.get()
        today = to_local(now).date()
        steps = sorted(((int(day), task_type) for task_type, day in (cfg.follow_up_days or {}).items()
                        if task_type in TASK_TYPES), reverse=True)
        result = {"follow_ups": 0, "lost": 0}
        candidates = Customer.objects(customer_state_now__in=[domain.PROPOSAL_SENT, 'NEGOTIATING'],
                                      human_operator__ne=True, proposal_sent_at__ne=None,
                                      funnel_entered_at__ne=None)
        for customer in candidates:
            cycle = self._cycle_key(customer)
            sent_day = to_local(customer.proposal_sent_at).date()
            elapsed = (today - sent_day).days

            if elapsed >= cfg.auto_lost_days and not self.customer_responded_since(customer, customer.proposal_sent_at):
                self._auto_lose(customer, now, cfg)
                result["lost"] += 1
                continue

            for day, task_type in steps:
                if elapsed < day:
                    continue
                if SdrTask.objects(customer=customer, type=task_type, metadata__cycle=cycle).first():
                    break
                older = [t for d, t in steps if d < day]
                if older:
                    SdrTask.objects(customer=customer, type__in=older, status='pending').update(set__status='canceled')
                due_at = business_slot(cfg.business_hours, sent_day + timedelta(days=day), cfg.first_call_hour) or now
                if self.create_task(str(customer.id), task_type, due_at=due_at, unique_pending=False,
                                    metadata={"cycle": cycle, "day": day}):
                    result["follow_ups"] += 1
                break
        return result

    def _auto_lose(self, customer: Customer, now: datetime, cfg: LmSettings) -> None:
        from crm.container import CrmContainer

        CrmContainer.get_pipeline_service().change_stage(
            str(customer.id), domain.LOST, lost_reason='sem_resposta', system=True,
            note=f"Sem resposta {cfg.auto_lost_days} dias depois da proposta.",
        )
        reactivate_on = to_local(now).date() + timedelta(days=cfg.reactivation_days)
        due_at = (business_slot(cfg.business_hours, reactivate_on, cfg.first_call_hour)
                  or now + timedelta(days=cfg.reactivation_days))
        self.create_task(str(customer.id), 'reativar_lead', due_at=due_at,
                         metadata={"lost_at": now.isoformat(), "proposal_sent_at": customer.proposal_sent_at.isoformat()})

    # --- Reunião amanhã ------------------------------------------------------------------------

    def create_meeting_tasks(self, now: datetime | None = None) -> int:
        """Reunião online ou visita técnica com lead marcada para amanhã: tarefa `reuniao_amanha`
        para a SDR confirmar com o cliente (uma por evento)."""
        from agenda.models import CalendarEvent

        now = now or datetime.utcnow()
        cfg = LmSettings.get()
        tomorrow = to_local(now).date() + timedelta(days=1)
        start = to_utc_naive(datetime.combine(tomorrow, datetime.min.time()))
        created = 0
        events = CalendarEvent.objects(status='confirmado', type__in=['reuniao_online', 'visita_tecnica'],
                                       customer__ne=None, start__gte=start, start__lt=start + timedelta(days=1))
        for event in events:
            if SdrTask.objects(type='reuniao_amanha', metadata__event_id=str(event.id)).first():
                continue
            task = self.create_task(
                str(event.customer.id), 'reuniao_amanha', unique_pending=False,
                due_at=first_call_due(cfg.business_hours, now, 0, cfg.first_call_hour),
                metadata={"event_id": str(event.id), "event_type": event.type, "event_start": event.start.isoformat()},
            )
            created += 1 if task else 0
        return created
