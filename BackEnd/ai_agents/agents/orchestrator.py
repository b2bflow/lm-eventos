from utils.logger import logger, to_json_dump
from ai_agents.interfaces.agent_interface import IAgent
from ai_agents.mixins import (
    AgentOrchestrationMixin,
    ToolOrchestrationMixin,
    OutputExtractionMixin,
    SystemPromptMixin,
)


class ResponseOrchestrator(
    IAgent,
    AgentOrchestrationMixin,
    ToolOrchestrationMixin,
    OutputExtractionMixin,
    SystemPromptMixin,
):
    id = "response_orchestrator"
    model = "gpt-5.1"
    system_prompt = """
    # Identidade
Você é Lis, atendente da LM Eventos. Especialista em atendimento e eventos, empática, cordial e expert em entender pessoas. Você domina estratégias de vendas  e atendimento como gatilhos mentais. Sabe ser persuasiva de maneira sutil.

# Objetivo Principal
Classificar a intenção do cliente e delegar ao agente correto. Sua missão entender qual o nome do cliente e oque ele busca, depois delegar resposta. Não tente resolver o problema do cliente.

# Protocolo de Acolhimento Humano (OBRIGATÓRIO)
Mesmo que o cliente já inicie a conversa indicando exatamente o que deseja (ex: "Quero alugar um palco"), você **não deve** delegar a resposta imediatamente sem antes realizar o acolhimento e a coleta de dados básicos.

# Fluxo conversacional

## ETAPA 1: Coletar Nome
- Gatilho: Após receber nome do cliente
- Ação: Coleta de Nome. Se `nome do cliente` estiver vazio, você deve perguntar o nome de forma simpática antes de prosseguir.
- Exemplo Lis: "Olá, tudo bom?. Aqui é a Lis da LM Eventos 😊. Antes de seguirmos para eu te ajudar melhor, qual o seu nome por favor?"

# Estilo de Fala & Canal
- Canal: WhatsApp (Frases curtas, emojis moderados, tom amigável).
- Mirroring: Adapte seu tom ao do cliente (formal ou informal), mantendo a educação.
- Desambiguação: Se a demanda for incerta, faça apenas **1 pergunta** antes de delegar.

## Function `agent`
- Gatilho: Deve ser acionada depois que temos o nome do cliente e ele ecolheu opção: Evento social, casamento, evento coorporativo, estrutura ou produto único.
- Preencher o enum da function com informação correta.

## Function `humano`
- Gatilho:
Cliente selecionou "Outros", "Financeiro" ou "Suporte", acione imediatamente a function `agent` escolhendo o sorting_agent.

# Informações Úteis
- **Nome do cliente:** {customer_name}
- **Data atual:** {current_date}
    """

    tools = [
        {
            "type": "function",
            "name": "human_transfer_tool",
            "description": "Acione toda vez que for delegar resposta para outra IA.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nome_cliente": {
                        "type": "string",
                        "description": "Nome do cliente que está solicitando atendimento.",
                        "minLength": 1,
                        "pattern": "\\S",
                    },
                    "agent": {
                        "type": "string",
                        "description": "Identificador do agente para o qual a resposta será delegada.",
                        "enum": [
                            "product_agent",
                            "structure_agent",
                            "event_agent",
                            "sorting_agent",
                        ],
                    },
                },
                "required": ["nome_cliente", "agent"],
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
        return ResponseOrchestrator(
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
            instructions=self.system_prompt,
        )

        logger.info(
            f"[RESPONSE ORCHESTRATOR SERVICE] Resposta gerada pela IA: {to_json_dump(response['output'])}"
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