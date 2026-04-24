from django.urls import path
from analytics.controllers.dashboard_controller import DashboardController

urlpatterns = [
    path('dashboard/metrics/', DashboardController.as_view(), name='dashboard_metrics'),
]