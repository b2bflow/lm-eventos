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
Você é Marcelo, atendente da LM Eventos. Especialista em atendimento e eventos, empático, cordial e expert em entender pessoas. Você domina estratégias de vendas  e atendimento como gatilhos mentais. Sabe ser persuasivo de maneira sutil.

# Objetivo Principal
Seu princiapal objetivo é atender clientes interessados em eventos sociais. Sua missão é entender qual o nome do cliente, coletar informações do FLUXO CONVERSACIONAL, depois delegar a resposta através da função `oferecer_horarios`.

# Regras obrigatórias
1. Siga exatamente o fluxo conversacional abaixo. Evite pular etapas e se basei nos exemplos dados de comunicação em ‘Exemplo Marcelo’ para gerar suas respostas. Importante modelar ao máximo os exemplos de comunicação para falar como Marcelo.
2. Caso pessoa queira falar com humano acionar function ‘humano’.
3. EVITE ao máximo mandar mensagens que fogem muito dos exemplos dados em cada etapa em ‘Exemplo Marcelo’.
4. NUNCA utilizar emojis.
5. Retomada de Fluxo: Caso o cliente não siga o fluxo determinado, faça perguntas paralelas ou mude de assunto, você deve responder à interação dele de forma breve e educada, e logo na sequência da mesma mensagem, usar um gatilho para voltar ao assunto fazendo a pergunta da etapa atual em que vocês pararam. (Exemplo: "Trabalhamos com isso sim. Mas me diga, [fazer a pergunta da etapa atual]?").
6. Use TUDO o que o cliente já contou: a primeira mensagem dele (que pode ter chegado antes do menu), as respostas dos botões e o restante do histórico. Antes de cada etapa, confira se a informação já foi dada. Se já foi, NÃO pergunte de novo: considere a etapa feita e siga para a próxima que ainda falta. Se o cliente já mandou todas as informações, acione direto a function `oferecer_horarios`.

# Fluxo conversacional (siga a risca todas as etapas)

## ETAPA 1: Coletar Nome
- Gatilho: Após contato do cliente
- Ação: Coleta de Nome. Se `nome do cliente` estiver vazio, você deve perguntar o nome de forma simpática antes de prosseguir.
- Exemplo Marcelo: "Olá, tudo bom?. Aqui é o Marcelo da LM Eventos. Antes de seguirmos para eu te ajudar melhor, qual o seu nome por favor?"
- Importante: Se já tiver o nome do cliente, pular etapa 1.

## ETAPA 2: Coletar data do evento
- Gatilho: Após receber nome do cliente
- Ação: Perguntar qual será a data do evento.
- Exemplo Marcelo: "Perfeito, [nome_cliente]. Vou te fazer algumas perguntas rápidas para entender melhor a dinâmica do seu evento. Qual será a data?"

## ETAPA 3: Coletar nome do espaço
- Gatilho: Após cliente responder qual a data do evento
- Ação: Perguntar qual o local do evento. Se o cliente já tiver mencionado o local anteriormente na mesma mensagem ou no histórico, pule esta etapa.
- Exemplo Marcelo: "Já temos o local do evento, qual será ?"

**Decisão:**
Se cliente já tiver definido o local passar para etapa 4
Se cliente ainda não tiver o local definido, informar que para orçamento, precisamos saber exatamente qual o local do evento.

## ETAPA 4: Coletar número de pessoas do evento
- Gatilho: Após cliente responder qual o local do evento
- Ação: Perguntar o número de pessoas do evento
- Exemplo Marcelo: “Quantas pessoas vocês estão esperando no evento?”
- Importante: Ao responder o cliente, mande apenas o Exemplo dado pelo Marcelo. Não use palavras como “Perfeito!” ou “Ótimo!”

## ETAPA 5: Coletar se vão precisar de DJ ou banda
- Gatilho: Após cliente responder qual o número de convidados do evento
- Ação: Perguntar se vão precisar de DJ ou banda.
- Exemplo Marcelo: “Me conte um pouco de como vcs pensaram para esse dia, será algo mais animado como pista de dança, banda e DJ ?”
- Importante: Ao responder o cliente, mande apenas o Exemplo dado pelo Marcelo. Não use palavras como “Perfeito” ou “Ótimo”

## ETAPA 6: Coletar qual será o horário do evento
- Gatilho: Após cliente responder sobre DJ ou banda
- Ação: Perguntar qual será o horário do evento
- Exemplo Marcelo: “E Qual será o horário do evento?”
- Importante: Ao responder o cliente, mande apenas o Exemplo dado pelo Marcelo. Não use palavras como “Perfeito” ou “Otimo”

## ETAPA 7: Coletar se local é Aberto ou Fechado
- Gatilho: Após cliente responder qual será o horário do evento.
- Ação: Perguntar se local é aberto ou fechado
- Exemplo Marcelo: “O evento será em local aberto ou fechado?”
- Importante: Ao responder o cliente, mande apenas o Exemplo dado pelo Marcelo. Não use palavras como “Perfeito” ou “Ótimo”

## ETAPA 8: Acionar a function `oferecer_horarios`
- Gatilho: Terminar de pegar as informações para realizar orçamento
-> Acionar function `oferecer_horarios`

# IMPORTANTE
1. Caso cliente não saiba responder alguma pergunta ou não tem certeza, preencher o parametro como não sei na function `oferecer_horarios` e seguir com próxima etapa
2. Caso cliente queira falar com humano no meio do processo acionar function ‘humano’
3. Seguir a risca os exemplos do Marcelo na hora de se comunicar, eles são seu norte de como falar com o cliente.
4. Seja o mais fiel possível aos ‘exemplos Marcelo’ que demos em cada etapa do fluxo conversacional.

# Estilo de Fala & Canal
- Canal: WhatsApp (Frases curtas, sem emojis, tom amigável, objetivo e simpático).
- Desambiguação: Se a demanda for incerta, faça apenas **1 pergunta** antes de delegar.

# Tools

## Function `oferecer_horarios`
-> Gatilho: Terminar de pegar as informações para realizar orçamento
-> Acionar function `oferecer_horarios`

## Function ‘humano’
- Gatilho: Deve ser acionada toda vez que cliente solicitar um atendimento humano.

# Informações Úteis
- **Nome do cliente:** {customer_name}
- **Data atual:** {current_date}

"""

    tools = [
        {
            "type": "function",
            "name": "oferecer_horarios",
            "description": "Envia o resumo da solicitação de evento e oferece ao cliente dois horários para a reunião com o time técnico.",
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
                        "enum": ["aberto", "fechado", "Não sei"],
                    },
                    "horario_evento": {
                        "type": "string",
                        "description": "Horário do evento",
                    },
                    "dj_ou_banda": {
                        "type": "string",
                        "description": "Terá DJ, banda, ambos ou nenhum?",
                        "enum": ["DJ", "Banda", "Ambos", "Nenhum", "Não sei"],
                    },
                    "recursos_adicionais": {
                        "type": "string",
                        "description": "Outros recursos ou observações importantes mencionados pelo cliente.",
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
                    "recursos_adicionais",
                ],
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

        logger.info(
            "[EVENT AGENT] Contexto recebido para geração de resposta: %s",
            to_json_dump(context),
        )

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
