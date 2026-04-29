from datetime import datetime
from bson import ObjectId
from mongoengine.queryset.visitor import Q
from crm.models.quote_model import Quote
from crm.models.custumer_model import Customer


class QuoteRepository:
    ACTIVE_STATUSES = ["ANALYSIS", "BUDGET", "NEGOTIATING"]

    def create(self, customer, attributes: dict | None = None) -> dict:
        quote = Quote(customer=customer)
        for key, value in (attributes or {}).items():
            if hasattr(quote, key):
                setattr(quote, key, value)
        quote.updated_at = datetime.utcnow()
        quote.save()
        return quote.to_dict()

    def create_document(self, customer, attributes: dict | None = None) -> Quote:
        quote = Quote(customer=customer)
        for key, value in (attributes or {}).items():
            if hasattr(quote, key):
                setattr(quote, key, value)
        quote.updated_at = datetime.utcnow()
        quote.save()
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
        return quote.to_dict()

    def list(self, status_filter: str | None = None, search_term: str | None = None) -> list[dict]:
        quotes = Quote.objects()

        if status_filter and status_filter != "all":
            quotes = quotes.filter(status=status_filter)

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

        return [quote.to_dict() for quote in quotes.order_by("-updated_at")]

    def delete(self, quote_id: str) -> bool:
        quote = self.get_document_by_id(quote_id)
        if not quote:
            return False
        quote.delete()
        return True
