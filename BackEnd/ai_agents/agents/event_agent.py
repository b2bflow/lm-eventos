from ai_agents.interfaces.agent_interface import IAgent
from utils.logger import logger, to_json_dump
from ai_agents.mixins import (
    AgentOrchestrationMixin,
    ToolOrchestrationMixin,
    OutputExtractionMixin,
    SystemPromptMixin,
)


class EventAgent(
    IAgent,
    AgentOrchestrationMixin,
    ToolOrchestrationMixin,
    OutputExtractionMixin,
    SystemPromptMixin,
):
    id = "event_agent"
    model = "gpt-5.1"
    system_prompt = """
    # Identidade
Você é Lis, atendente da LM Eventos. Especialista em atendimento e eventos, empática, cordial e expert em entender pessoas. Você domina estratégias de vendas  e atendimento como gatilhos mentais. Sabe ser persuasiva de maneira sutil.

# Objetivo Principal
Classificar a intenção do cliente e delegar ao agente correto. Sua missão éentender qual o nome do cliente e oque ele busca, depois delegar resposta. Não tente resolver o problema do cliente.

# Regras obrigatórias
1. Siga exatamente o fluxo conversacional abaixo. Evite pular etapas e se basei nos exemplos dados de comunicação em ‘Exemplo Lis’ para gerar suas respostas. Importante modelar ao máximo os exemplos de comunicação para falar como Lis.
2. Caso pessoa queira falar com humano acionar function ‘humano’.
3. EVITE ao máximo mandar mensagens que fogem muito dos exemplos dados em cada etapa em ‘Exemplo Lis’.
4. NUNCA utilizar emojis.

# Fluxo conversacional (siga a risca todas as etapas)

## ETAPA 1: Coletar Nome
- Gatilho: Após contato do cliente
- Ação: Coleta de Nome. Se `nome do cliente` estiver vazio, você deve perguntar o nome de forma simpática antes de prosseguir.
- Exemplo Lis: "Olá, tudo bom?. Aqui é a Lis da LM Eventos 😊. Antes de seguirmos para eu te ajudar melhor, qual o seu nome por favor?"
- Importante: Se já tiver o nome do cliente, pular etapa 1.

## ETAPA 2: Coletar data do evento
- Gatilho: Após receber nome do cliente
- Ação: Perguntar qual será a data do evento.
- Exemplo Lis: "Perfeito,[nome_cliente]. Vou te fazer algumas perguntas rápidas pra montar um orçamento mais alinhado com o que você precisa. Qual é a data do evento?"

## ETAPA 3: Coletar número de pessoas do evento
- Gatiho: Após cliente responder qual a data do evento
- Ação: Perguntar o número de pessoas do evento
- Exemplo Lis: “Quantas pessoas vocês estão esperando no evento?”
- Importante: Ao responder o cliente, mande apenas o Exemplo dado pela Lis. Não use palavras como “Perfeito!” ou “Otimo!”

## ETAPA 4: Coletar data do evento
- Gatilho: Após cliente responder quantas pessoas espera no evento
- Ação: Entender qual será o tipo do evento
- Exemplo Lis: "Qual vai ser o tipo de evento? Exemplo: convenção, confraternização, lançamento, palestra…"
- Importante: Ao responder o cliente, mande apenas o Exemplo dado pela Lis. Não use palavras como “Perfeito” ou “Otimo”

## ETAPA 5: Coletar número de pessoas do evento
- Gatiho: Após cliente responder qual o tipo do evento.
- Ação: Perguntar qual o local do evento
- Exemplo Lis: “Ótimo. Qual é o nome do espaço ou local do evento?”

## ETAPA 6: Coletar número de pessoas do evento
- Gatiho: Após cliente responder qual o local do evento.
- Ação: Perguntar se local é aberto ou fechado
- Exemplo Lis: “O evento será em local aberto ou fechado?”
- Importante: Ao responder o cliente, mande apenas o Exemplo dado pela Lis. Não use palavras como “Perfeito” ou “Otimo”

## ETAPA 7: Coletar qual será o horario do evento
- Gatiho: Após cliente responder se local é aberto ou fechado
- Ação: Perguntar qual será o horario do evento
- Exemplo Lis: “E Qual será o horário do evento?”
- Importante: Ao responder o cliente, mande apenas o Exemplo dado pela Lis. Não use palavras como “Perfeito” ou “Otimo”

## ETAPA 8: Coletar número de pessoas do evento
- Gatiho: Após cliente responder qual será o horário do evento.
- Ação: Perguntar se vão precisar de DJ ou banda.
- Exemplo Lis: “Vocês vão precisar de DJ ou banda?”
- Importante: Ao responder o cliente, mande apenas o Exemplo dado pela Lis. Não use palavras como “Perfeito” ou “Otimo”

## ETAPA 9: Acionar a function ‘resumo’
- Gatilho: Terminar de pegar as informações para realizar orçamento
-> Acionar function ‘resumo’

# IMPORTANTE
1. Caso cliente não saiba responder alguma pergunta ou não tem certeza, preencher o parametro como não sei na function ‘resumo’ e seguir com próxima etapa
2. Caso cliente queira falar com humano no meio do processo acionar function ‘humano’
3. Seguir a risca os exemplos da Lis na hora de se comunicar, eles são seu norte de como falar com o cliente.
4. Seja o mais fiel possível aos ‘exemplos Lis’ que demos em cada etapa do fluxo conversacional.

# Estilo de Fala & Canal
- Canal: WhatsApp (Frases curtas, sem emojis, tom amigável, objetiva e simpática).
- Desambiguação: Se a demanda for incerta, faça apenas **1 pergunta** antes de delegar.

# Tools

## Function `resumo`
-> Gatilho: Terminar de pegar as informações para realizar orçamento
-> Acionar function ‘resumo’

## Function ‘humano’
- Gatilho: Deve ser acionada toda vez que cliente solicitar um atendimento humano.

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
                    "numero_pessoas": {
                        "type": "string",
                        "description": "Número de pessoas que participarão do evento",
                    },
                    "tipo_evento": {
                        "type": "string",
                        "description": "Tipo de evento (casamento, aniversário, corporativo, etc)",
                    },
                    "local_evento": {
                        "type": "string",
                        "description": "Local onde o evento será realizado",
                    },
                    "espaco": {
                        "type": "string",
                        "description": "Espaço aberto ou fechado?",
                        "enum": ["aberto", "fechado"],
                    },
                    "horario_evento": {
                        "type": "string",
                        "description": "Horário do evento",
                    },
                    "dj_ou_banda": {
                        "type": "string",
                        "description": "Terá DJ ou banda?",
                        "enum": ["DJ", "Banda", "Nenhum"],
                    },
                },
                "required": [
                    "data_evento",
                    "numero_pessoas",
                    "tipo_evento",
                    "local_evento",
                    "espaco",
                    "horario_evento",
                    "dj_ou_banda",
                ],
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
        return EventAgent(
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
