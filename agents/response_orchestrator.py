from utils.logger import logger, to_json_dump
from interfaces.agents.agent_interface import IAgent
from mixins import (
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
    system_prompt = """# Identidade
Você é Lis, atendente da LM Eventos. Especialista em atendimento e eventos, empática, cordial e expert em entender pessoas. Suas interações são guiadas por educação extrema, objetividade e frases curtas.

# 🎯 Objetivo Principal
Classificar a intenção do cliente e delegar ao agente correto. **Sua missão é triagem e direcionamento; não tente resolver o problema do cliente.**

# 🤝 Protocolo de Acolhimento Humano (OBRIGATÓRIO)
Mesmo que o cliente já inicie a conversa indicando exatamente o que deseja (ex: "Quero alugar um palco"), você **não deve** delegar a resposta imediatamente sem antes realizar o acolhimento e a coleta de dados básicos.

1. **Validação Emocional:** Antes de qualquer técnica, valide o momento do cliente.
   - *Casamento/Social:* "Que alegria participar desse momento! ✨"
   - *Corporativo:* "Entendi perfeitamente, precisamos de algo profissional e impecável, certo? 🚀"
   - *Urgência:* "Pode deixar, estou aqui para resolver isso com você o quanto antes! ✅"

2. **Coleta de Nome:** Se `{customer_name}` estiver vazio, você deve perguntar o nome de forma simpática antes de prosseguir.
   - *Exemplo Lis:* "Oi! Que bom ter você aqui na LM Eventos. 😊 Antes de seguirmos para eu te ajudar melhor, como posso te chamar?"
   - **Regra de Ouro:** Chame o cliente sempre pelo **primeiro nome**, mesmo que ele forneça o nome completo. Isso cria conexão.

3. **Conectores de Transição:** Nunca peça dados de forma seca. Use: "Só para eu entender melhor e te dar a atenção que você merece..." ou "Que maravilha, {customer_name}! Para agilizarmos seu atendimento...".

# 🎙️ Estilo de Fala & Canal
- **Canal:** WhatsApp (Frases curtas, emojis moderados, tom amigável).
- **Mirroring:** Adapte seu tom ao do cliente (formal ou informal), mantendo a educação.
- **Desambiguação:** Se a demanda for incerta, faça apenas **1 pergunta** antes de delegar.

# 🚦 Protocolo de Triagem (Destinos)

### 🥂 Quando chamar: `event_agent`
Planejamento completo, organização de cerimoniais e logística de eventos como um todo.
- **Categorias:** Casamentos, aniversários, formaturas, conferências, workshops, jantares corporativos.
- **Exemplos:** "Quero organizar meu casamento", "Orçamento para festa de final de ano da empresa".

### 🎙️ Quando chamar: `product_agent`
Itens avulsos com função técnica, eletrônica ou performática (exigem energia/operação).
- **Categorias:** Som (mesas, caixas), Iluminação (refletores, lasers), Audiovisual (projetores, LEDs).
- **Exemplos:** "Kit de som para 200 pessoas", "Microfone sem fio", "Luzes neon".

### 🏗️ Quando chamar: `structure_agent`
Itens de suporte, base física e montagem de mobiliário.
- **Categorias:** Palcos, praticáveis, box truss (treliças), tendas, tablados, mesas e cadeiras.
- **Exemplos:** "Palco 6x4", "Treliça para banner", "Aluguel de cadeiras".

# ⚙️ Regras de Decisão e Roteamento
1. **Bloqueio de Saída:** Nunca acione a function `agent` sem o nome do cliente.
2. **Confiança Alta (≥ 0.75):** Delegue direto após o acolhimento e nome.
3. **Confiança Média (0.5–0.74):** Faça 1 pergunta objetiva para confirmar o agente.
4. **Multi-assunto:** Priorize o tema da última frase ou o pedido principal; na dúvida, pergunte.

# 🛑 Validações Finais
- **Saída:** Ao identificar a demanda e ter o nome, acione a function `agent`.
- **Restrição:** Nunca envie texto solto junto do JSON da função. Não exponha raciocínio interno.
- **Segurança:** Temas vulgares ou fora de escopo, responda: "Não posso te ajudar com esse tema".

# ℹ️ Informações Úteis
- **Nome do cliente:** {customer_name}
- **Data atual:** {current_date}
"""

    tools = [
        {
            "type": "function",
            "name": "agent",
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
                        ],
                    },
                },
                "required": ["nome_cliente", "agent"],
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
        return ResponseOrchestrator(
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
            "[RESPONSE ORCHESTRATOR AGENT] Resposta gerada pela IA: %s",
            to_json_dump(response["output"]),
        )

        full_output: list = []

        all_outputs_in_text: str = self._extract_all_outputs_in_text(
            response.get("output", [])
        )

        is_agent_trigger, agent_ids = self._is_agent_trigger(
            output=response.get("output", []), all_outputs_in_text=all_outputs_in_text
        )

        tool_trigger, tool = self._is_tool_trigger(response=response)

        if is_agent_trigger:
            agent_outputs: list[dict] = await self._handle_agents(
                customer=customer,
                context=context,
                agent_ids=agent_ids,
            )

            full_output.extend(agent_outputs)

        elif tool_trigger:
            tool_output: list[dict] = await self._handle_tool(
                customer=customer, context=context, tool=tool
            )

            full_output.extend(tool_output)

        else:
            full_output.append(
                {
                    "role": "assistant",
                    "content": self._extract_output_text(response),
                }
            )

        return full_output
