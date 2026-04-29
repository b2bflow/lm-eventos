from django.urls import path, include
from rest_framework.routers import DefaultRouter
from crm.controllers.customer_controller import CustomerController
from crm.controllers.quote_controller import QuoteController

router = DefaultRouter()
router.register(r'customers', CustomerController, basename='customer')
router.register(r'leads', CustomerController, basename='lead_alias') # Alias para o React
router.register(r'quotes', QuoteController, basename='quote')
router.register(r'cotacoes', QuoteController, basename='quote_alias')

urlpatterns = [
    path('', include(router.urls)),
]
