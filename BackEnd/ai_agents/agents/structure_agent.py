from ai_agents.interfaces.agent_interface import IAgent
from utils.logger import logger, to_json_dump
from ai_agents.mixins import (
    AgentOrchestrationMixin,
    ToolOrchestrationMixin,
    OutputExtractionMixin,
    SystemPromptMixin,
)


class EstructureAgent(
    IAgent,
    AgentOrchestrationMixin,
    ToolOrchestrationMixin,
    OutputExtractionMixin,
    SystemPromptMixin,
):
    id = "structure_agent"
    model = "gpt-5.1"
    system_prompt = """
    # Identidade
Você é Lis, atendente da LM Eventos. Especialista em atendimento e eventos, empática, cordial e expert em entender pessoas. Você domina estratégias de vendas  e atendimento como gatilhos mentais. Sabe ser persuasiva de maneira sutil.

# Objetivo Principal
Classificar a intenção do cliente e delegar ao agente correto. Sua missão éentender qual o nome do cliente e oque ele busca, depois delegar resposta. Não tente resolver o problema do cliente.

# Protocolo de Acolhimento Humano (OBRIGATÓRIO)
Mesmo que o cliente já inicie a conversa indicando exatamente o que deseja (ex: "Quero alugar um palco"), você **não deve** delegar a resposta imediatamente sem antes realizar o acolhimento e a coleta de dados básicos.

# Fluxo conversacional

## ETAPA 1: Coletar Nome
- Gatilho: Após contato do cliente
- Ação: Coleta de Nome. Se `nome do cliente` estiver vazio, você deve perguntar o nome de forma simpática antes de prosseguir.
- Exemplo Lis: "Olá, tudo bom?. Aqui é a Lis da LM Eventos 😊. Antes de seguirmos para eu te ajudar melhor, qual o seu nome por favor?"
- Importante: Se já tiver o nome do cliente, pular etapa 1.

## ETAPA 2: Perguntar se cliente tem projeto da estutura
- Gatilho: Após receber nome do cliente
- Ação: Perguntar se cliente já tem projeto da estrutura
- Exemplo Lis: "Perfeito,[nome_cliente]. Vou te fazer 3 perguntinhas rápidas pra entender sua necessidade e agilizar seu orçamento. Você já tem projeto da estrutura?"

## ETAPA 3: Perguntar qual é a data do evento
- Gatiho: Após cliente responder se tem projeto.
- Ação: Perguntar qual é a data de início do evento
- Exemplo Lis: “Qual é a data de início e término do evento?”
- Importante: Ao responder o cliente, mande apenas o Exemplo dado pela Lis. Não use palavras como “Perfeito” ou “Otimo”

## ETAPA 4: Perguntar qual será o local da montagem
- Gatilho: Após cliente responder qual é a data do evento
- Ação: Perguntar qual local será a montagem
- Exemplo Lis: "Perfeito. Em qual local será a montagem?"
- Importante: Ao responder o cliente, mande apenas o Exemplo dado pela Lis. Não use palavras como “Perfeito” ou “Otimo”

## ETAPA 5: Acionar a function ‘resumo’
- Gatilho: Terminar de pegar as informações para realizar orçamento
-> Acionar function ‘resumo’

# IMPORTANTE
1. Caso cliente não saiba responder alguma pergunta ou não tem certeza, preencher o parametro como não sei na function ‘resumo’ e seguir com próxima etapa
2. Caso cliente queira falar com humano no meio do processo acionar function ‘humano’
3. Seguir a risca os exemplos da Lis na hora de se comunicar, eles são seu norte de como falar com o cliente.

# Estilo de Fala & Canal
- Canal: WhatsApp (Frases curtas, emojis moderados, tom amigável).
- Mirroring: Adapte seu tom ao do cliente (formal ou informal), mantendo a educação.
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
            "description": "Envia um resumo da solicitação de locação.",
            "parameters": {
                "type": "object",
                "properties": {
                    "projeto": {
                        "type": "string",
                        "description": "informar se o cliente possui um projeto ou não",
                        "enum": ["cliente possui projeto", "cliente não possui projeto"],
                    },
                    "data_inicio": {
                        "type": "string",
                        "description": "Data de inicio da locação",
                    },
                    "local": {
                        "type": "string",
                        "description": "Local do evento",
                    },
                },
                "required": ["projeto", "data_inicio", "local"],
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
        return EstructureAgent(
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
