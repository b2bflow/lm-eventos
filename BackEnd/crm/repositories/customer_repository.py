from datetime import datetime, timedelta

from crm.phones import phone_variants
from crm.models.custumer_model import Customer
from crm.interfaces.customer_repository_interface import ICustomerRepository
from database.client.mongodb_client import MongoDBClient
from bson import ObjectId
from mongoengine.queryset.visitor import Q


class CustomerRepository(ICustomerRepository):
    UPDATABLE_FIELDS = frozenset([
        "name", "phone", "agent", "customer_state_now", "celebration_type", "event_title",
        "event_date", "guest_count", "quoted_amount", "contract_value", "venue", "notes",
        "proposal_sent_at", "last_interaction_at", "next_step", "customer_custom_tag", "new_service",
        # Funil LM
        "email", "company", "role", "contact_type", "origin", "owner", "human_operator", "product",
        "qualification", "pending_fields", "attachments", "flags", "needs_erica", "lost_reason",
        "next_action_at", "qualified_at", "first_contact_at", "stage_changed_at",
        # Fluxo da IA em producao
        "blocked_until", "silenced_until", "send_button", "waiting_for_name", "name_collected",
        "last_message_attendant", "followup_sent",
    ])

    def __init__(self, database_client: MongoDBClient):
        self.db = database_client

    def get_customers(self, ids: list[str]) -> list[dict]:
        with self.db.get_connection_context():
            if not ids:
                return []

            # Converte strings para ObjectId
            object_ids = []
            for id_str in ids:
                try:
                    object_ids.append(ObjectId(id_str))
                except:
                    continue

            customers = Customer.objects(id__in=object_ids)
            return [customer.to_dict() for customer in customers]

    def get_all_customers(
        self,
        status_filter: str | None = None,
        search_term: str | None = None,
        custom_tag_filter: str | None = None,
    ) -> list[dict]:
        with self.db.get_connection_context():
            customers = Customer.objects()

            if status_filter and status_filter != 'all':
                customers = customers.filter(customer_state_now=status_filter)

            if custom_tag_filter and custom_tag_filter != 'all':
                customers = customers.filter(customer_custom_tag=custom_tag_filter)

            if search_term:
                customers = customers.filter(
                    Q(name__icontains=search_term) |
                    Q(phone__icontains=search_term) |
                    Q(event_title__icontains=search_term) |
                    Q(celebration_type__icontains=search_term)
                )

            customers = customers.order_by('-updated_at')
            return [customer.to_dict() for customer in customers]

    def page_customers(self, status_filter: str | None = None, search_term: str | None = None,
                       offset: int = 0, limit: int = 10, custom_tag_filter: str | None = None) -> tuple[list[dict], int]:
        from crm import domain
        with self.db.get_connection_context():
            customers = Customer.objects()
            if status_filter and status_filter != 'all':
                legacy = [old for old in domain.LEGACY_STAGES if domain.resolve_legacy_stage(old) == status_filter]
                customers = customers.filter(customer_state_now__in=[status_filter, *legacy])
            if custom_tag_filter and custom_tag_filter != 'all':
                customers = customers.filter(customer_custom_tag=custom_tag_filter)
            if search_term:
                customers = customers.filter(
                    Q(name__icontains=search_term) |
                    Q(phone__icontains=search_term) |
                    Q(event_title__icontains=search_term) |
                    Q(celebration_type__icontains=search_term) |
                    Q(company__icontains=search_term)
                )
            total = customers.count()
            page = customers.order_by('-updated_at').skip(offset).limit(limit)
            return [customer.to_dict() for customer in page], total

    def find(self, id: str | None = None, phone: str | None = None) -> dict | None:
        with self.db.get_connection_context():
            query_params = {}

            if id:
                try:
                    query_params["id"] = ObjectId(id)
                except:
                    return None

            if phone:
                query_params["phone"] = phone

            customer = Customer.objects(**query_params).first()

            return customer.to_dict() if customer else None


    def find_user_by_mongo_logic(self, **kwargs) -> dict | None:
        with self.db.get_connection_context():
            customer = Customer.objects(**kwargs).first()

            return customer.to_dict() if customer else None

    def get_customer_by_filters(self, **kwargs) -> dict | None:
        with self.db.get_connection_context():
            customer = Customer.objects(**kwargs)

            return [customer.to_dict() for customer in customer]

    def create(
        self,
        name: str,
        phone: str | list,
        agent: str | None = None,
    ) -> dict:
        with self.db.get_connection_context():
            customer = Customer(
                name=name,
                phone=phone,
                agent=agent
            )
            customer.save()
            return customer.to_dict()

    def update_name(
        self,
        name: str,
        phone: str,
    ) -> bool:
        with self.db.get_connection_context():
            # Mesmo celular com e sem o nono dígito é o mesmo contato.
            customer = Customer.objects(phone__in=phone_variants(phone) or [phone]).order_by('created_at').first()
            if not customer:
                return False

            customer.name = name
            customer.save()
            return True

    def update(
        self,
        id: str,
        attributes: dict = {},
    ) -> dict | None:
        with self.db.get_connection_context():
            customer = Customer.objects(id=ObjectId(id)).first()
            if not customer:
                return None

            for key, value in attributes.items():
                if key in self.UPDATABLE_FIELDS:
                    setattr(customer, key, value)

            customer.updated_at = attributes.get("updated_at", customer.updated_at)
            customer.save()
            return customer.to_dict()

    def claim_new_service(self, customer_id: str) -> bool:
        """
        Tenta marcar new_service como False atomicamente.
        Retorna True apenas para o primeiro processo concorrente que conseguir alterar.
        """
        with self.db.get_connection_context():
            try:
                result = Customer.objects(
                    id=ObjectId(customer_id),
                    new_service=True
                ).update_one(set__new_service=False)
                return bool(result > 0)
            except Exception:
                return False

    def exists(self, phone: str) -> bool:
        with self.db.get_connection_context():
            return Customer.objects(phone=phone).count() > 0

    def get_customers_needing_follow_up(self) -> list[dict]:

        four_hours_ago = datetime.now() - timedelta(hours=4)

        with self.db.get_connection_context():
            customers = Customer.objects(
                last_message_attendant__lte=four_hours_ago,
                followup_sent=False,
            )

        return [customer.to_dict() for customer in customers]

    def get_by_id(self, id: str) -> dict | None:
        with self.db.get_connection_context():
            try:
                customer = Customer.objects(id=ObjectId(id)).first()
                return customer.to_dict() if customer else None
            except:
                return None

    def get_by_phone(self, phone: str) -> dict | None:
        with self.db.get_connection_context():
            # Mesmo celular com e sem o nono dígito é o mesmo contato.
            customer = Customer.objects(phone__in=phone_variants(phone) or [phone]).order_by('created_at').first()
            return customer.to_dict() if customer else None

    def delete_customer(self, customer_id: str) -> bool:
        with self.db.get_connection_context():
            customer = Customer.objects(id=ObjectId(customer_id)).first()
            if not customer:
                return False

            customer.delete()
            return True
