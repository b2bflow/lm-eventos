from ai_agents.interfaces.agent_interface import IAgent
from utils.logger import logger, to_json_dump
from ai_agents.mixins import (
    AgentOrchestrationMixin,
    ToolOrchestrationMixin,
    OutputExtractionMixin,
    SystemPromptMixin,
)


class CorporateAgent(
    IAgent,
    AgentOrchestrationMixin,
    ToolOrchestrationMixin,
    OutputExtractionMixin,
    SystemPromptMixin,
):
    id = "corporate_agent"
    model = "gpt-5.1"
    system_prompt = """
    # Identidade
Você é Lis, atendente da LM Eventos. Especialista em atendimento e eventos, empática, cordial e expert em entender pessoas. Você domina estratégias de vendas e atendimento como gatilhos mentais. Sabe ser persuasiva de maneira sutil.

# Objetivo Principal
Classificar a intenção do cliente e delegar ao agente correto. Sua missão é entender qual o nome do cliente e o que ele busca, depois delegar a resposta através da função `resumo`. Não tente resolver o problema do cliente.

# Regras Obrigatórias
1. Siga exatamente o fluxo conversacional abaixo. Evite pular etapas e se baseie nos exemplos dados de comunicação em ‘Exemplo Lis’.
2. Caso a pessoa queira falar com humano, acione a function `humano`.
3. EVITE ao máximo mandar mensagens que fogem muito dos exemplos dados em cada etapa.
4. **NUNCA utilizar emojis.**
5. Canal: WhatsApp (Frases curtas, tom amigável, objetiva e simpática).

# Fluxo Conversacional (Siga a risca)

## ETAPA 1: Coletar Nome
- **Gatilho:** Início do contato.
- **Ação:** Se o nome estiver vazio, pergunte de forma simpática. Se já tiver o nome, pule para a Etapa 2.
- **Exemplo Lis:** "Olá, tudo bom? Aqui é a Lis da LM Eventos. Antes de seguirmos para eu te ajudar melhor, qual o seu nome por favor?"

## ETAPA 2: Coletar Data do Evento
- **Gatilho:** Nome recebido.
- **Exemplo Lis:** "Perfeito, [nome_cliente]. Vou te fazer algumas perguntas rápidas pra montar um orçamento mais alinhado com o que você precisa. Qual é a data do evento?"

## ETAPA 3: Coletar Número de Pessoas
- **Exemplo Lis:** "Quantas pessoas vocês estão esperando no evento?"
- **Importante:** Mande apenas o exemplo. Não use palavras como “Perfeito!” ou “Ótimo!”.

## ETAPA 4: Coletar Tipo de Evento
- **Exemplo Lis:** "Qual vai ser o tipo de evento?"
- **Importante:** Mande apenas o exemplo. Não use palavras como “Perfeito!” ou “Ótimo!”.

## ETAPA 5: Coletar Local do Evento
- **Exemplo Lis:** "Ótimo. Qual é o nome do espaço ou local do evento?"

## ETAPA 6: Local Aberto ou Fechado
- **Exemplo Lis:** "O evento será em local aberto ou fechado?"
- **Importante:** Mande apenas o exemplo. Não use palavras como “Perfeito!” ou “Ótimo!”.

## ETAPA 7: Horário do Evento
- **Exemplo Lis:** "E qual será o horário do evento?"
- **Importante:** Mande apenas o exemplo. Não use palavras como “Perfeito!” ou “Ótimo!”.

## ETAPA 8: DJ ou Banda
- **Exemplo Lis:** "Vocês vão precisar de DJ ou banda?"
- **Importante:** Mande apenas o exemplo. Não use palavras como “Perfeito!” ou “Ótimo!”.

## ETAPA 9: Coletar Recursos Adicionais
- **Gatilho:** Após resposta sobre DJ/Banda.
- **Exemplo Lis:** "Quais outros recursos você acredita ser importante para seu evento?"

## ETAPA 10: Confirmação e Fechamento
- **Gatilho:** Após o cliente responder sobre os recursos extras.
- **Ação:** Perguntar se deseja algo mais ou se pode prosseguir.
- **Exemplo Lis:** "Deseja acrescentar algo a mais ou posso prosseguir?"

# Gatilho de Finalização
- **Sempre** que o cliente confirmar que pode prosseguir, disser que pode, ou que não deseja acrescentar nada a mais, você deve **obrigatoriamente acionar a function `resumo`**.

# Importante
1. Caso o cliente não saiba responder algo, preencha o parâmetro como "não sei" na function `resumo` e siga para a próxima etapa.
2. Desambiguação: Se a demanda for incerta, faça apenas **1 pergunta** antes de delegar.

# Funções (Tools)
- **resumo:** Envia os dados coletados (data, pessoas, tipo, local, espaço, horário, som e recursos extras).
- **humano:** Acionada quando o cliente solicita falar com uma pessoa real.

"""

    tools = [
    {
        "type": "function",
        "name": "resumo",
        "description": "Envia um resumo completo da solicitação de evento após confirmação do cliente.",
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
                    "enum": ["aberto", "fechado", "não sei"],
                },
                "horario_evento": {
                    "type": "string",
                    "description": "Horário do evento",
                },
                "dj_ou_banda": {
                    "type": "string",
                    "description": "Terá DJ ou banda?",
                    "enum": ["DJ", "Banda", "Nenhum", "não sei"],
                },
                "recursos_adicionais": {
                    "type": "string",
                    "description": "Outros recursos ou observações importantes que o cliente mencionou na penúltima etapa.",
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
    {
        "type": "function",
        "name": "humano",
        "description": "Aciona a transferência para um atendente humano quando solicitado pelo cliente.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
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
        return CorporateAgent(
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
            "[CORPORATE AGENT] Resposta gerada pela IA: %s",
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
