from utils.logger import logger, to_json_dump
from interfaces.agents.agent_interface import IAgent
from mixins import (
    AgentOrchestrationMixin,
    ToolOrchestrationMixin,
    OutputExtractionMixin,
    SystemPromptMixin,
)


class PoolAgent(
    IAgent,
    AgentOrchestrationMixin,
    ToolOrchestrationMixin,
    OutputExtractionMixin,
    SystemPromptMixin,
):
    id = "event_agent"
    model = "gpt-5.1"
    system_prompt = """# Identidade
Você é Lis, atendente da LM Eventos. Especialista em atendimento e equipamentos técnicos (som, iluminação, audiovisual). Você entende de pessoas, é empática, cordial e usa frases curtas e objetivas.

# Objetivo
Identificar qual equipamento técnico o cliente deseja e coletar as informações necessárias para o orçamento.

# Estilo de Fala (WhatsApp)
- Energética, simpática e educada.
- Frases curtas e amigáveis.
- **Princípios:** Uma pergunta por mensagem. Aguarde a resposta. Trate pelo nome `{customer_name}`. Não repita informações.

# Verificações importates
- Sempre que receber uma data, verifique se ela é uma data futura. Se for uma data passada, corrija a informação perguntando: "Parece que a data informada já passou. Poderia confirmar a data correta do evento?". Utilize a variável `{current_date}` para ter acesso ao dia atual.

# Fluxo Obrigatório de Coleta
Siga esta ordem, uma pergunta por vez:
1. Data do evento.
2. Local do evento (Endereço Ou nome do espaço).
3. Horário do evento.
4. Espaço aberto ou fechado?
5. Numero de convidados.
6. Tipo de evento (casamento, aniversário, corporativo, etc) Pegunte apenas se não tiver essa infromação.
7. Se terá DJ ou banda.


# Transbordo e Finalização
- **Function `resumo`:** Acione apenas quando tiver TODAS as informações acima (Data, Local, Horário, Espaco, Convidados, Tipo de evento, DJ ou banda, Descrição).
- **Function `orquestrador`:** Acione IMEDIATAMENTE se o cliente solicitar uma demanda fora de equipamentos técnicos (ex: palcos, tendas, tablados) ou qualquer assunto fora de sua responsabilidade.

# Informações Úteis
- **Nome do cliente:** {customer_name}
- **Data atual:** {current_date}
"""

    tools = [
        {
            "type": "function",
            "name": "resumo",
            "description": "Envia um resumo da solicitação de evento.",
            "parameters": {
                "type": "object",
                "properties": {
                    "data_evento": {
                        "type": "string",
                        "description": "Data do evento",
                    },
                    "local_evento": {
                        "type": "string",
                        "description": "Local do evento (Endereço Ou nome do espaço)",
                    },
                    "horario_evento": {
                        "type": "string",
                        "description": "Horário do evento",
                    },
                    "espaco": {
                        "type": "string",
                        "description": "Espaço aberto ou fechado?",
                        "enum": ["aberto", "fechado"],
                    },
                    "numero_convidados": {
                        "type": "integer",
                        "description": "Numero de convidados",
                    },
                    "tipo_evento": {
                        "type": "string",
                        "description": "Tipo de evento (casamento, aniversário, corporativo, etc)",
                    },
                    "dj_ou_banda": {
                        "type": "string",
                        "description": "Terá DJ ou banda?",
                        "enum": ["DJ", "Banda", "Nenhum"],
                    },
                },
                "required": ["data_evento", "local_evento", "horario_evento", "espaco", "numero_convidados", "tipo_evento", "dj_ou_banda"],
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
        return PoolAgent(
            agent_container=agent_container,
            tool_container=tool_container,
            message_repository=repository_container.message,
            ai_client=client_container.ai,
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

        is_tool_trigger, tool = self._is_tool_trigger(response=response)

        if is_agent_trigger:
            agent_outputs: list[dict] = await self._handle_agents(
                customer=customer,
                context=context,
                agent_ids=agent_ids,
            )

            full_output.extend(agent_outputs)

        elif is_tool_trigger:
            tool_outputs: list[dict] = await self._handle_tool(
                customer=customer, context=context, tool=tool
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
