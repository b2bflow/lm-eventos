from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView
from users.controllers.auth_controller import CustomTokenObtainPairView, AuthController
from users.controllers.user_controller import UserController
from users.controllers.request_controller import NameRequestController
from users.controllers.team_controller import TeamController

router = DefaultRouter()
router.register(r'usuarios', UserController, basename='usuario')
router.register(r'name_requests', NameRequestController, basename='name_request')
router.register(r'teams', TeamController, basename='team')

urlpatterns = [
    path('token/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'), 
    path('logout/', AuthController.as_view({'post': 'logout'}), name='logout'),    
    path('me/', UserController.as_view({'get': 'me'}), name='me'),   
    path('update_profile/', UserController.as_view({'patch': 'update_profile'}), name='update_profile'),
    path('change_password/', UserController.as_view({'post': 'change_password'}), name='change_password'),
    
    path('', include(router.urls)),
]