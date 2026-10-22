from django.urls import path

from sales.controllers import (
    CalculateController, CatalogController, ProposalActionController, ProposalDetailController, ProposalListController,
    PriceSettingsController, ProposalPdfController,
)

urlpatterns = [
    path('catalog/', CatalogController.as_view(), name='sales-catalog'),
    path('prices/', PriceSettingsController.as_view(), name='sales-prices'),
    path('proposals/calculate/', CalculateController.as_view(), name='proposal-calculate'),
    path('proposals/', ProposalListController.as_view(), name='proposal-list'),
    path('proposals/<str:proposal_id>/', ProposalDetailController.as_view(), name='proposal-detail'),
    path('proposals/<str:proposal_id>/pdf/', ProposalPdfController.as_view(), name='proposal-pdf'),
    path('proposals/<str:proposal_id>/pdf/<str:file_name>', ProposalPdfController.as_view(), name='proposal-pdf-named'),
    path('proposals/<str:proposal_id>/<str:action>/', ProposalActionController.as_view(), name='proposal-action'),
]
