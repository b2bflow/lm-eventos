from ai_agents.interfaces.agent_interface import IAgent
from utils.logger import logger, to_json_dump
from ai_agents.mixins import (
    AgentOrchestrationMixin,
    ToolOrchestrationMixin,
    OutputExtractionMixin,
    SystemPromptMixin,
)


class SortingAgent(
    IAgent,
    AgentOrchestrationMixin,
    ToolOrchestrationMixin,
    OutputExtractionMixin,
    SystemPromptMixin,
):
    id = "sorting_agent"
    model = "gpt-5.1"
    system_prompt = """
    # Identidade
Você é Lis, atendente da LM Eventos. Especialista em atendimento e eventos, empática, cordial e expert em entender pessoas. Você domina estratégias de vendas e atendimento como gatilhos mentais, sendo persuasiva de forma sutil.

# Objetivo Principal
Seu objetivo é:
1. Coletar o nome do cliente (caso ainda não tenha)
2. Entender o motivo real do contato
3. Confirmar que o atendimento será encaminhado para um humano

⚠️ Não faça nada além disso.

# Contexto de Entrada
O cliente já selecionou uma dessas opções:
"Outros", "Financeiro" ou "Suporte"

⚠️ Importante:
Essas opções NÃO representam o motivo real, são apenas palavras-chave.
Você deve descobrir o motivo verdadeiro conversando com o cliente.

# Restrições
- É PROIBIDO deduir o motivo sem ter perguntado ao cliente
- É PROIBIDO confirmar encaminhamento sem:
- ter o nome do cliente
- entender claramente o motivo
- Não pular etapas
- Não assumir o problema sem confirmação

# Fluxo Conversacional

## ETAPA 1: Coletar Nome
- Se `{customer_name}` estiver vazio:
  - Pergunte o nome de forma natural
  - Aguarde resposta antes de continuar

### Exemplo (seguir estilo, não copiar sempre igual):
"Oi, tudo bem? 😊  
Aqui é a Lis da LM Eventos. Antes de te ajudar melhor, como posso te chamar?"

## ETAPA 2: Entender Motivo do Contato
- Inicia após ter o nome
- Faça **1 pergunta natural e aberta**
- Evite linguagem robótica ou formato de menu

### Exemplos (usar como referência de estilo):

Genérico:
"{customer_name}, me conta rapidinho como posso te ajudar 😊"

Mais direcionado (sem parecer menu):
"{customer_name}, isso é sobre pagamento ou algo relacionado a evento/estrutura?"

Mais aberto:
"{customer_name}, pode me explicar um pouquinho melhor o que aconteceu?"

## ETAPA 3: Confirmar encaminhamento
- Após entender claramente o motivo

### Ação:
Responder de forma curta que vai encaminhar para o time humano com base no que foi informado.

### Exemplos de motivo:
- "Dúvida sobre pagamento pendente"
- "Problema com equipamento em evento"
- "Solicitação de parceria"

# Estilo de Fala & Canal
- Canal: WhatsApp
- Frases curtas e naturais
- Tom amigável e humano
- Emojis moderados (sem exagero)
- Mirroring: adaptar ao estilo do cliente

# Regra de Naturalidade (CRÍTICA)
- Não soar como robô
- Não usar listas de opções
- Não repetir frases iguais sempre
- Conduzir como conversa real

# Informações Úteis
- Nome do cliente: {customer_name}
- Data atual: {current_date}

"""

    tools = [
        {
            "type": "function",
            "name": "humano",
            "description": "Acione toda vez que for delegar resposta para um atendente humano.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nome_cliente": {
                        "type": "string",
                        "description": "Nome do cliente que está solicitando atendimento.",
                    },
                    "motivo": {
                        "type": "string",
                        "description": "Problema que o cliente deseja resolver.",
                    },
                },
                "required": ["nome_cliente", "motivo"],
                "additionalProperties": False,
            },
            "strict": True,
        },
        {
            "type": "function",
            "name": "orquestrador",
            "description": "Aciona a função para casos fora do domínio de conhecimento.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
            "strict": True,
        },
    ]

    @staticmethod
    def factory(
        agent_container,
        tool_container,
        client_container,
        repository_container,
    ) -> "IAgent":
        return SortingAgent(
            agent_container=agent_container,
            tool_container=tool_container,
            message_repository=repository_container.message,
            ai_client=client_container.ai(),
        )

    async def execute(self, context: list, customer: dict) -> list[dict]:
        context = self._insert_system_prompt(customer, context)

        response = self.ai.create_model_response(
            model=self.model,
            input=context,
            tools=self.tools,
            instructions=self.instructions,
        )

        logger.info(
            "[EVENT AGENT] Resposta gerada pela IA: %s",
            to_json_dump(response["output"]),
        )

        full_output: list = []

        all_outputs_in_text: str = self._extract_all_outputs_in_text(
            response.get("output", [])
        )

        is_agent_trigger, agent_ids = self._is_agent_trigger(
            output=response.get("output", []), all_outputs_in_text=all_outputs_in_text
        )

        is_tool_trigger, tools = self._is_tool_trigger(response=response)

        if is_agent_trigger:
            agent_outputs: list[dict] = await self._handle_agents(
                customer=customer,
                context=context,
                agent_ids=agent_ids,
            )

            full_output.extend(agent_outputs)

        elif is_tool_trigger:
            tool_outputs: list[dict] = await self._handle_tools(
                customer=customer, context=context, tools=tools
            )

            full_output.extend(tool_outputs)

        else:
            full_output.append(
                {
                    "role": "assistant",
                    "content": self._extract_output_text(response),
                }
            )

        return full_output
