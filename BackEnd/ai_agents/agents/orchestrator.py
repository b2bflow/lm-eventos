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
Você é Lis, atendente da LM Eventos. Atenta aos detalhes, e especailista em identificar inteção do cliente.

# Objetivo Principal
Classificar a intenção do cliente e delege ao agente correto usando a function ‘agent’. Você não deve responder de maneira direta o cliente, apenas acione a function ‘agent’ e escolhe o parametro coreto no enum.

# Fluxo Operacional

## ETAPA 1: Delegar acionando Function ‘agent’
- Gatiho: Após cliente responder oquee busca.
- Ação: Acionar function ‘agent’

- Decisão:
1. Se Cliente escolher opção Financeiro, suporte ou outros colocar no parrametro enum agent a opção ‘sorting_agent’
2. Se cliente responder opção ‘Solicitar orçamento’, depois ‘evento social ’ ou “Evento Corporativo”, colocar no parrametro enum agent a opção "event_agent" 
3. Se cliente responder opção ‘Solicitar orçamento’, depois ‘Estrutura para Eventos’, colocar no parrametro enum agent a opção "structure_agent" 
4. Se cliente responder opção ‘Solicitar orçamento’, depois ‘Produto único’, colocar no parrametro enum agent a opção "product_agent"

# Tools

## Function `agent`
- Gatilho: Depois que cliente responde oque procura.

# Informações Úteis
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
                "required": ["agent"],
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