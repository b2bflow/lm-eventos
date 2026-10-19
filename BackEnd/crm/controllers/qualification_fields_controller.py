from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from crm import domain
from crm.services.lead_qualification_service import COMMON_FIELDS, MIRRORS, PRODUCT_FIELDS


class QualificationFieldsController(APIView):
    """GET /crm/qualification/fields/: campos aceitos por save_field, por produto."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({
            "common": list(COMMON_FIELDS),
            "products": {p: list(PRODUCT_FIELDS.get(p, ())) for p in domain.PRODUCTS},
            "mirrors": MIRRORS,
        })
