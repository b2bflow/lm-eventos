from __future__ import annotations
from datetime import datetime
from bson import ObjectId
from mongoengine.queryset.visitor import Q
from crm.models.quote_model import Quote
from crm.models.custumer_model import Customer
from utils.logger import logger
from crm.services.quote_sync import sync_customer_from_quote


class QuoteRepository:
    ACTIVE_STATUSES = ["ANALYSIS", "BUDGET", "NEGOTIATING", "WON", "LOST", "WAITING_BUDGET"]

    def create(self, customer, attributes: dict | None = None) -> dict:
        quote = Quote(customer=customer)
        for key, value in (attributes or {}).items():
            if hasattr(quote, key):
                setattr(quote, key, value)
        quote.updated_at = datetime.utcnow()
        quote.save()
        sync_customer_from_quote(quote)
        return quote.to_dict()

    def create_document(self, customer, attributes: dict | None = None) -> Quote:
        quote = Quote(customer=customer)
        for key, value in (attributes or {}).items():
            if hasattr(quote, key):
                setattr(quote, key, value)
        quote.updated_at = datetime.utcnow()
        quote.save()
        sync_customer_from_quote(quote)
        return quote

    def get_by_id(self, quote_id: str) -> dict | None:
        try:
            quote = Quote.objects(id=ObjectId(quote_id)).first()
            return quote.to_dict() if quote else None
        except Exception:
            return None

    def get_document_by_id(self, quote_id: str) -> Quote | None:
        try:
            return Quote.objects(id=ObjectId(quote_id)).first()
        except Exception:
            return None

    def get_active_by_customer(self, customer) -> Quote | None:
        return Quote.objects(customer=customer, status__in=self.ACTIVE_STATUSES).order_by("-updated_at").first()

    def update(self, quote_id: str, attributes: dict) -> dict | None:
        quote = self.get_document_by_id(quote_id)
        if not quote:
            return None

        for key, value in attributes.items():
            if hasattr(quote, key):
                setattr(quote, key, value)

        quote.updated_at = attributes.get("updated_at", datetime.utcnow())
        quote.save()
        sync_customer_from_quote(quote)
        return quote.to_dict()

    def _build_queryset(
        self,
        status_filter: str | None = None,
        search_term: str | None = None,
        custom_tag_filter: str | None = None,
    ):
        quotes = Quote.objects()

        if status_filter and status_filter != "all":
            quotes = quotes.filter(status=status_filter)

        if custom_tag_filter and custom_tag_filter != "all":
            matching_customers = Customer.objects(customer_custom_tag=custom_tag_filter).only("id")
            quotes = quotes.filter(customer__in=list(matching_customers))

        if search_term:
            matching_customers = Customer.objects(
                Q(name__icontains=search_term) | Q(phone__icontains=search_term)
            ).only("id")
            quotes = quotes.filter(
                Q(event_title__icontains=search_term)
                | Q(celebration_type__icontains=search_term)
                | Q(venue__icontains=search_term)
                | Q(customer__in=list(matching_customers))
            )

        return quotes

    def _serialize(self, quotes) -> list[dict]:
        quotes = list(quotes)
        customer_ids = {quote.customer_ref_id() for quote in quotes} - {None}
        customers = {customer.id: customer for customer in Customer.objects(id__in=list(customer_ids))}

        results = []
        for quote in quotes:
            customer = customers.get(quote.customer_ref_id())
            if not customer:
                logger.warning(f"[QuoteRepository] Ignorando cotação órfã {quote.id}: cliente inexistente.")
                continue
            results.append(quote.to_dict(customer=customer))
        return results

    def list(
        self,
        status_filter: str | None = None,
        search_term: str | None = None,
        custom_tag_filter: str | None = None,
    ) -> list[dict]:
        quotes = self._build_queryset(status_filter, search_term, custom_tag_filter).order_by("-updated_at")
        return self._serialize(quotes)

    def list_page(
        self,
        status_filter: str | None = None,
        search_term: str | None = None,
        custom_tag_filter: str | None = None,
        page: int = 1,
        page_size: int = 10,
    ) -> tuple[int, list[dict]]:
        quotes = self._build_queryset(status_filter, search_term, custom_tag_filter)
        total_count = quotes.count()
        page_quotes = quotes.order_by("-updated_at").skip((page - 1) * page_size).limit(page_size)
        return total_count, self._serialize(page_quotes)

    def list_created_between(self, start_dt: datetime, end_dt: datetime) -> list[dict]:
        quotes = Quote.objects(created_at__gte=start_dt, created_at__lte=end_dt)
        return self._serialize(quotes)

    def count(self) -> int:
        return Quote.objects().count()

    def delete(self, quote_id: str) -> bool:
        quote = self.get_document_by_id(quote_id)
        if not quote:
            return False
        quote.delete()
        return True
