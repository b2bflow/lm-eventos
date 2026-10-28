from django.urls import path

from inventory.controllers import (
    AvailabilityController, InventoryItemAdjustController, InventoryItemDetailController, InventoryItemsController,
    InventoryObservationsController, KitDetailController, KitReserveController, KitsController, MovementsController,
    ReservationDetailController, ReservationsController,
)

urlpatterns = [
    path('items/', InventoryItemsController.as_view(), name='inventory-items'),
    path('items/<str:item_id>/', InventoryItemDetailController.as_view(), name='inventory-item'),
    path('items/<str:item_id>/adjust/', InventoryItemAdjustController.as_view(), name='inventory-item-adjust'),
    path('items/<str:item_id>/observations/', InventoryObservationsController.as_view(),
         name='inventory-item-observations'),
    path('items/<str:item_id>/observations/<str:observation_id>/', InventoryObservationsController.as_view(),
         name='inventory-item-observation'),
    path('kits/', KitsController.as_view(), name='inventory-kits'),
    path('kits/<str:kit_id>/', KitDetailController.as_view(), name='inventory-kit'),
    path('kits/<str:kit_id>/reserve/', KitReserveController.as_view(), name='inventory-kit-reserve'),
    path('availability/', AvailabilityController.as_view(), name='inventory-availability'),
    path('reservations/', ReservationsController.as_view(), name='inventory-reservations'),
    path('reservations/<str:reservation_id>/', ReservationDetailController.as_view(), name='inventory-reservation'),
    path('movements/', MovementsController.as_view(), name='inventory-movements'),
]
