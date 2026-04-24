from django.urls import path, include
from rest_framework.routers import DefaultRouter
from crm.controllers.customer_controller import CustomerController

router = DefaultRouter()
router.register(r'customers', CustomerController, basename='customer')
router.register(r'leads', CustomerController, basename='lead_alias') # Alias para o React

urlpatterns = [
    path('', include(router.urls)),
]
