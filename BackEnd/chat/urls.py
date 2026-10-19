from django.urls import path
from chat.controllers.chat_controller import (
    ConversationAssignController, ConversationCallController, ConversationModeController, ConversationNoteController,
    ConversationViewSet, MessageFileUploadView, MessageViewSet,
)
from chat.controllers.system_config_controller import SystemConfigController

# Conversas e mensagens são o histórico do atendimento (e da IA): sem PUT/DELETE e sem criar
# conversa pela API. Conversa nasce no webhook; mudanças passam pelo PATCH (ler, fechar, reabrir)
# e pelas ações da equipe abaixo, que validam e registram quem fez.
conversation_list = ConversationViewSet.as_view({
    'get': 'list',
})

conversation_detail = ConversationViewSet.as_view({
    'get': 'retrieve',
    'patch': 'partial_update',
})

# Mensagem do operador entra pelo POST (vai para a Z-API); mensagens gravadas não são editadas.
message_list = MessageViewSet.as_view({
    'get': 'list',
    'post': 'create'
})

message_detail = MessageViewSet.as_view({
    'get': 'retrieve',
})

system_config = SystemConfigController.as_view({
    'get': 'list',
    'post': 'create'
})

contact_search = ConversationViewSet.as_view({'get': 'search_contacts'})
conversation_start = ConversationViewSet.as_view({'post': 'start_conversation'})

# 4. Declaramos as URLs mapeando para as variáveis acima
urlpatterns = [
    # --- Rotas Oficiais (Inglês) ---
    path('conversations/', conversation_list, name='conversation-list'),
    path('contacts/search/', contact_search, name='chat-contact-search'),
    path('conversations/start/', conversation_start, name='conversation-start'),
    path('conversations/<str:pk>/', conversation_detail, name='conversation-detail'),
    path('conversations/<str:pk>/mode/', ConversationModeController.as_view(), name='conversation-mode'),
    path('conversations/<str:pk>/assign/', ConversationAssignController.as_view(), name='conversation-assign'),
    path('conversations/<str:pk>/notes/', ConversationNoteController.as_view(), name='conversation-notes'),
    path('conversations/<str:pk>/calls/', ConversationCallController.as_view(), name='conversation-calls'),
    
    path('messages/', message_list, name='message-list'),
    path('messages/files/', MessageFileUploadView.as_view(), name='message-file-upload'),
    path('messages/<str:pk>/', message_detail, name='message-detail'),

    path('configuracoes/', system_config, name='system-config'),

    # --- Aliases (Português) ---
    path('conversas/', conversation_list, name='conversa_alias-list'),
    path('conversas/<str:pk>/', conversation_detail, name='conversa_alias-detail'),
    
    path('mensagens/', message_list, name='mensagem_alias-list'),
    path('mensagens/arquivos/', MessageFileUploadView.as_view(), name='mensagem-file-upload-alias'),
    path('mensagens/<str:pk>/', message_detail, name='mensagem_alias-detail'),
]
