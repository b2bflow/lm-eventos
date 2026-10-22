from django.urls import path, include
from rest_framework.routers import DefaultRouter
from crm.controllers.customer_controller import CustomerController
from crm.controllers.quote_controller import QuoteController
from crm.controllers.qualification_fields_controller import QualificationFieldsController
from crm.controllers.contact_controller import (
    ContactDetailController, ContactImportController, ContactListController, ContactNewLeadController,
    ContactTimelineController,
)
from crm.controllers.funnel_controller import (
    FunnelBoardController, FunnelListController, FunnelMetaController, LmSettingsController, SdrTaskController,
)

router = DefaultRouter()
router.register(r'customers', CustomerController, basename='customer')
router.register(r'leads', CustomerController, basename='lead_alias') # Alias para o React
router.register(r'quotes', QuoteController, basename='quote')
router.register(r'cotacoes', QuoteController, basename='quote_alias')

urlpatterns = [
    path('funnel/', FunnelBoardController.as_view(), name='funnel-board'),
    path('funnel/list/', FunnelListController.as_view(), name='funnel-list'),
    path('meta/', FunnelMetaController.as_view(), name='funnel-meta'),
    path('tasks/', SdrTaskController.as_view(), name='sdr-tasks'),
    path('tasks/<str:task_id>/done/', SdrTaskController.as_view(), name='sdr-task-done'),
    path('settings/', LmSettingsController.as_view(), name='lm-settings'),
    path('contacts/', ContactListController.as_view(), name='contacts'),
    path('contacts/import-partners/', ContactImportController.as_view(), name='contacts-import'),
    path('contacts/<str:contact_id>/', ContactDetailController.as_view(), name='contact-detail'),
    path('contacts/<str:contact_id>/new-lead/', ContactNewLeadController.as_view(), name='contact-new-lead'),
    path('contacts/<str:contact_id>/timeline/', ContactTimelineController.as_view(), name='contact-timeline'),
    path('qualification/fields/', QualificationFieldsController.as_view(), name='qualification-fields'),
    path('', include(router.urls)),
]
