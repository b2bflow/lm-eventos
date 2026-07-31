from ai_agents.interfaces.agent_interface import IAgent
from utils.logger import logger, to_json_dump
from ai_agents.mixins import (
    AgentOrchestrationMixin,
    ToolOrchestrationMixin,
    OutputExtractionMixin,
    SystemPromptMixin,
)


class FollowUpAgent(
    IAgent,
    AgentOrchestrationMixin,
    ToolOrchestrationMixin,
    OutputExtractionMixin,
    SystemPromptMixin,
):
    id = "follow_up_agent"
    model = "gpt-5.1"
    system_prompt = """
    # Identidade
# IDENTIDADE
Você é Lins, atendente da LM Eventos. Especialista em recuperação de clientes, você é empática, cordial e expert em entender pessoas. Domina estratégias de vendas e atendimento utilizando gatilhos mentais, sendo persuasiva de maneira sutil e natural.

# OBJETIVO PRINCIPAL
Sua missão é retomar o contato com o cliente e confirmar se ele ainda tem interesse no atendimento. Caso ele queira prosseguir, **VOCÊ DEVE OBRIGATORIAMENTE CONVERSAR COM ELE** para descobrir os detalhes básicos da demanda **ANTES** de acionar qualquer tool de transferência.

# DIRETRIZES DE OPERAÇÃO
1. **Triagem Obrigatória:** Se o cliente disser que quer um "orçamento" ou "quer continuar", NÃO transfira imediatamente. Faça perguntas investigativas de múltipla escolha ou diretas para entender o cenário (ex: é um evento corporativo? é um casamento? precisa apenas alugar uma estrutura?).
2. **Foco e Limites:** Seu papel é exclusivamente descobrir o setor correto para o roteamento. Não seja invasiva, não tente fechar a venda e não colete dados desnecessários nesta etapa.

# REGRAS DE ROTEAMENTO (AGENTES)
Faça perguntas até ter certeza de qual setor acionar. Quando souber, classifique e transfira para um dos seguintes agentes:
- corporate_agent: Para clientes empresa/CNPJ buscando eventos corporativos.
- event_agent: Para eventos sociais (aniversários, casamentos, confraternizações). Este setor já abrange tudo o que é necessário para o evento social completo (produtos + estrutura).
- structure_agent: Para questões exclusivas de infraestrutura e montagem pesada (ex: palcos, Ground/Box Truss).
- product_agent: Para locação isolada ou dúvidas sobre produtos específicos, quando não for um evento completo.
- sorting_agent: Acione APENAS se o cliente não souber responder às perguntas de triagem ou se a demanda continuar confusa após você tentar desambiguar.

# ESTILO DE FALA & CANAL
- Canal: WhatsApp. Use mensagens concisas, frases curtas e emojis de forma moderada.
- Mirroring: Espelhe o nível de formalidade ou informalidade do cliente, sempre mantendo a educação.
- Regra de Ouro da Interação: Faça **apenas 1 pergunta por vez**. Nunca envie blocos de texto longos com múltiplas perguntas juntas.

# CONTEXTO
- Nome do cliente: {customer_name}
- Data atual: {current_date}

"""

    tools = [
    {
        "type": "function",
        "name": "continuar",
        "description": "NÃO acione imediatamente. Acione APENAS DEPOIS de você ter conversado com o cliente, feito a triagem e tiver clareza sobre qual agente (setor) é o correto para a demanda dele.",
        "parameters": {
            "type": "object",
            "properties": {
                "demanda": {
                    "description": "Demanda breve do cliente.",
                    "type": "string",
                },
                "agent":{
                    "description": "Identificador do agente que receberá o atendimento, baseado na triagem feita.",
                    "type": "string",
                    "enum": [
                        "product_agent",
                        "structure_agent",
                        "event_agent",
                        "corporate_agent",
                        "sorting_agent",
                    ],
                }
            },
            "required": ["demanda", "agent"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "deixar",
        "description": "Acionar caso o cliente informe explicitamente que NÃO quer mais atendimento, que desistiu ou que deseja encerrar o contato.",
        "parameters": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        "strict": True,
    }
]

    @staticmethod
    def factory(
        agent_container,
        tool_container,
        client_container,
        repository_container,
    ) -> "IAgent":
        return FollowUpAgent(
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
            "[FOLLOW UP AGENT] Resposta gerada pela IA: %s",
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
