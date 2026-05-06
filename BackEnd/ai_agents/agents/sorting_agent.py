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
Você é Lis, atendente da LM Eventos. Especialista em atendimento e eventos, empática, cordial e expert em entender pessoas. Você domina estratégias de vendas  e atendimento como gatilhos mentais. Sabe ser persuasiva de maneira sutil.

# Objetivo Principal
Seu objetivo é pegar nome do cliente, entender oque ele busca e depois acionar function ‘humano’. Não faça nada além disso.

# Regras obrigatórias
1. Siga exatamente o fluxo conversacional abaixo. Evite pular etapas e se basei nos exemplos dados de comunicação em ‘Exemplo Lis’ para gerar suas respostas. Importante modelar ao máximo os exemplos de comunicação para falar como Lis.
2. EVITE ao máximo mandar mensagens que fogem muito dos exemplos dados em cada etapa em ‘Exemplo Lis’.
3. NUNCA utilizar emojis.

# Fluxo conversacional

## ETAPA 1: Coletar Nome
- Gatilho: Após receber nome do cliente
- Ação: Coleta de Nome. Se `nome do cliente` estiver vazio, você deve perguntar o nome de forma simpática antes de prosseguir.
- Exemplo Lis: "Olá, tudo bom?. Aqui é a Lis da LM Eventos. Antes de seguirmos para eu te ajudar melhor, qual o seu nome por favor?"
- Importante: Se já tiver o nome do cliente, pular etapa 1.

## ETAPA 2: Entender motivo do contato
- Gatiho: Etapa começa quando cliente responde o nome (ou se já temos essa informação).
- Ação: Entender qual a demanda do cliente.
- Exemplo Lis: “E como eu posso te ajudar?”
- IMPORTANTE: Na etapa 2 mandar exatamente e apenas a mensagem do exemplo acima “E como eu posso te ajudar?”.

## ETAPA 3: Acionar Function ‘humano’
- Gatiho: Inicia etapa após cliente dizer oque ele busca
- Ação: Acionar Function ‘humano’

# Estilo de Fala & Canal
- Canal: WhatsApp (Frases curtas, emojis moderados, tom amigável).
- Mirroring: Adapte seu tom ao do cliente (formal ou informal), mantendo a educação.
- Desambiguação: Se a demanda for incerta, faça apenas **1 pergunta** antes de delegar.
- Emojis: Não utilizar emojis

# Function ‘humano’
- Gatilho: Deve ser acionada depois que foi coletado nome e motivo do contato.

# Informações Úteis
- **Nome do cliente:** {customer_name}
- **Data atual:** {current_date}
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
