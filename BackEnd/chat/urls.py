from django.urls import path
from chat.controllers.chat_controller import ConversationViewSet, MessageViewSet

# 1. Definimos o que acontece quando batem na rota principal (sem ID)
conversation_list = ConversationViewSet.as_view({
    'get': 'list',
    'post': 'create'
})

# 2. Definimos o que acontece quando batem na rota com ID
conversation_detail = ConversationViewSet.as_view({
    'get': 'retrieve',
    'put': 'update',
    'patch': 'partial_update',
    'delete': 'destroy'
})

# 3. Repetimos o processo para as Mensagens
message_list = MessageViewSet.as_view({
    'get': 'list',
    'post': 'create'
})

message_detail = MessageViewSet.as_view({
    'get': 'retrieve',
    'put': 'update',
    'patch': 'partial_update',
    'delete': 'destroy'
})

# 4. Declaramos as URLs mapeando para as variáveis acima
urlpatterns = [
    # --- Rotas Oficiais (Inglês) ---
    path('conversations/', conversation_list, name='conversation-list'),
    path('conversations/<str:pk>/', conversation_detail, name='conversation-detail'),
    
    path('messages/', message_list, name='message-list'),
    path('messages/<str:pk>/', message_detail, name='message-detail'),

    # --- Aliases (Português) ---
    path('conversas/', conversation_list, name='conversa_alias-list'),
    path('conversas/<str:pk>/', conversation_detail, name='conversa_alias-detail'),
    
    path('mensagens/', message_list, name='mensagem_alias-list'),
    path('mensagens/<str:pk>/', message_detail, name='mensagem_alias-detail'),
]