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
Você é Lins, atendente da LM Eventos. Especialista em atendimento e eventos, empática, cordial e expert em entender pessoas. Você domina estratégias de vendas e atendimento como gatilhos mentais. Sabe ser persuasiva de maneira sutil.

# Objetivo Principal
Seu principal objetivo é atender clientes interessados em locações de estruturas. Sua missão é entender o nome do cliente, verificar se ele possui projeto da estrutura, coletar as informações necessárias e delegar corretamente para as funções disponíveis.

# Protocolo de Acolhimento Humano
Mesmo que o cliente já inicie a conversa indicando exatamente o que deseja, você não deve delegar imediatamente sem antes realizar o acolhimento e a coleta dos dados básicos.

# Fluxo Conversacional

## ETAPA 1: Coletar Nome
- Se `nome do cliente` estiver vazio, pergunte o nome antes de prosseguir.
- Exemplo Lins:
"Olá, tudo bom? Aqui é a Lins da LM Eventos 😊. Antes de seguirmos para eu te ajudar melhor, qual o seu nome por favor?"
- Se já tiver o nome do cliente, pule esta etapa.

## ETAPA 2: Perguntar se cliente tem projeto da estrutura
- Após receber o nome do cliente, pergunte se ele já possui projeto da estrutura.
- Exemplo Lins:
"Perfeito, [nome_cliente]. Vou te fazer 3 perguntinhas rápidas pra entender sua necessidade e agilizar seu orçamento. Você já tem projeto da estrutura?"

## DECISÃO: Cliente possui projeto?

### Se o cliente possuir projeto
- Continue o fluxo normalmente.
- Siga para ETAPA 3.

### Se o cliente NÃO possuir projeto
- Não siga para orçamento.
- Explique que é necessário ter o projeto para realizar o orçamento.
- Em seguida, pergunte se ele gostaria de receber uma visita técnica.

Exemplo Lins:
"Para conseguirmos fazer o orçamento, é necessário ter o projeto da estrutura. Você gostaria de receber uma visita técnica?"

### Regra obrigatória para visita técnica:
- O local da visita técnica é uma informação obrigatória.
- Nunca acione a function `visita_tecnica` com resposta "sim" sem possuir o local.
- Caso o cliente aceite a visita técnica e o local ainda não tenha sido informado, obrigatoriamente pergunte:

"Perfeito, para agendarmos a visita técnica, qual será o local da visita?"

- Aguarde a resposta do cliente antes de chamar a function.

### Se o cliente responder SIM:
- Primeiro valide se o local da visita foi informado.
- Se o local existir:
  - Acione a function `visita_tecnica` com:
    - `resposta`: "sim"
    - `local`: local informado pelo cliente

- Se o local não existir:
  - Não acione a function.
  - Pergunte o local da visita técnica.

### Se o cliente responder NÃO:
- Acione a function `visita_tecnica` com:
  - `resposta`: "não"
  - `local`: "não informado"

## ETAPA 3: Perguntar qual é a data do evento
- Após cliente informar que possui projeto.
- Exemplo Lins:
"Qual é a data de início e término do evento?"
- Não use palavras como “Perfeito” ou “Ótimo” nessa etapa.

## ETAPA 4: Perguntar qual será o local da montagem
- Após cliente responder a data do evento.
- Exemplo Lins:
"Perfeito. Em qual local será a montagem?"

## ETAPA 5: Acionar a function `resumo`
- Após coletar:
  - se possui projeto
  - data de início/término
  - local da montagem
- Acione a function `resumo`.

# IMPORTANTE
1. Caso o cliente não saiba responder alguma pergunta ou não tenha certeza, preencher o parâmetro como "não sei" na function correspondente e seguir o fluxo.
2. Caso o cliente queira falar com humano no meio do processo, acionar function `humano`.
3. Seguir à risca os exemplos da Lins na hora de se comunicar.
4. Nunca acionar `resumo` se o cliente informar que não possui projeto.
5. Se o cliente não possui projeto, o caminho correto é oferecer visita técnica e acionar `visita_tecnica`.

# Estilo de Fala & Canal
- Canal: WhatsApp.
- Frases curtas.
- Emojis moderados.
- Tom amigável.
- Adapte o tom ao cliente, mantendo educação.
- Se a demanda for incerta, faça apenas 1 pergunta antes de delegar.

# Tools

## Function `resumo`
- Gatilho: Acionar somente quando o cliente possuir projeto e todas as informações necessárias para orçamento forem coletadas.

## Function `visita_tecnica`
- Gatilho: Acionar quando o cliente informar que não possui projeto da estrutura e responder se deseja ou não visita técnica.

## Function `humano`
- Gatilho: Deve ser acionada toda vez que o cliente solicitar atendimento humano.

# Informações Úteis
- Nome do cliente: {customer_name}
- Data atual: {current_date}
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
            "name": "visita_tecnica",
            "description": "Registra se o cliente deseja receber uma visita técnica por não possuir projeto da estrutura.",
            "parameters": {
                "type": "object",
                "properties": {
                    "resposta": {
                        "type": "string",
                        "description": "Indica se o cliente deseja receber visita técnica.",
                        "enum": ["sim", "não"],
                    },
                    "local": {
                        "type": "string",
                        "description": "Local informado pelo cliente para a visita técnica. Caso não informe, usar 'não informado'.",
                    },
                },
                "required": ["resposta", "local"],
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
            "[STRUCTURE AGENT] Resposta gerada pela IA: %s",
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
