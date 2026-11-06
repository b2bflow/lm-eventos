"""Agente de agendamento (06/11): continua a conversa depois de `oferecer_horarios` (social e corporativo).

Entende a resposta do cliente aos horários oferecidos e chama a ferramenta certa. As mensagens de
agendamento, os horários livres e o limite de tentativas ficam nas ferramentas (meeting_booking_tools).
"""
from datetime import datetime, timedelta

from ai_agents.interfaces.agent_interface import IAgent
from ai_agents.mixins import OutputExtractionMixin, ToolOrchestrationMixin
from ai_agents.tools.meeting_booking_tools import MEETING_AGENT, offered_slots
from crm.models.custumer_model import Customer
from crm.services.business_hours import to_local
from agenda.services.free_slots import WEEKDAYS, describe_slot
from utils.logger import logger, to_json_dump


def _calendar(now_local: datetime, days: int = 14) -> str:
    return "\n".join(
        f"- {WEEKDAYS[d.weekday()]}: {d:%d/%m/%Y}"
        for d in (now_local.date() + timedelta(days=i) for i in range(days))
    )


def _offered(slots: list[datetime], now: datetime) -> str:
    if not slots:
        return "- (nenhum horário foi oferecido; o cliente foi perguntado qual o melhor dia e horário)"
    return "\n".join(
        f"- {to_local(s):%d/%m/%Y %H:%M} ({describe_slot(s, now)})" for s in slots
    )


class MeetingAgent(IAgent, ToolOrchestrationMixin, OutputExtractionMixin):
    id = MEETING_AGENT
    model = "gpt-5.1"
    system_prompt = """
# Identidade
Você é Marcelo, atendente da LM Eventos. Empático, cordial e objetivo. Canal: WhatsApp (frases curtas, sem emojis).

# Situação
Você já coletou as informações do evento do cliente e ofereceu horários para uma reunião de 40 minutos com o
nosso time técnico. Agora o seu único trabalho é entender a resposta do cliente sobre o horário e acionar a
function certa. Você NÃO escreve a mensagem de agendamento: as functions já respondem o cliente.

# Horários oferecidos ao cliente (horário de Brasília)
{offered}

# Hoje
{now} (horário de Brasília)

# Próximos dias
{calendar}

# Como decidir
1. O cliente aceitou um dos horários oferecidos ("pode ser", "o primeiro", "quinta às 10h fica ótimo"):
   acione `agendar_reuniao` com a data e o horário escolhidos.
   - Se ele só disser "pode ser" e foram oferecidos dois horários, pergunte qual dos dois ele prefere.
2. O cliente não consegue nos horários oferecidos, mas já disse um dia e horário (ou só um horário):
   acione `agendar_reuniao` com o que ele disse. A function confere se está livre.
   - Se ele disse só o horário, sem o dia, deixe `data` vazio.
   - "Amanhã", "sexta", "dia 12": converta para a data usando a lista "Próximos dias".
3. O cliente só consegue num período ("só à tarde", "de manhã", "à noite") ou num dia, sem dizer o horário
   ("só consigo na sexta"): acione `oferecer_outros_horarios` com o período e/ou a data.
4. O cliente não consegue nos horários oferecidos e não disse outro ("não consigo nesses horários"):
   acione `perguntar_horario` com motivo "horarios".
5. O cliente não consegue no dia oferecido e não disse outro ("não consigo nesse dia"):
   acione `perguntar_horario` com motivo "dia".
6. O cliente pediu para falar com uma pessoa, desistiu da reunião ou o assunto não é o horário da reunião
   e você não consegue resolver numa frase: acione `humano`.
7. Pergunta rápida sobre a reunião (ex.: "é online?", "quanto tempo dura?"): responda em uma frase
   (a reunião é online, por vídeo, e dura cerca de 40 minutos) e pergunte se algum dos horários fica bom.

# Regras
- NUNCA invente que a reunião está marcada: só a function `agendar_reuniao` marca.
- NUNCA ofereça horários por conta própria: horários novos vêm só de `oferecer_outros_horarios`.
- Acione no máximo uma function por resposta.
- Nunca use emojis.

# Cliente
- Nome do cliente: {customer_name}
"""

    tools = [
        {
            "type": "function",
            "name": "agendar_reuniao",
            "description": "Marca a reunião no dia e horário que o cliente escolheu (um dos oferecidos ou um que ele disse). Confere se o horário está livre e responde o cliente.",
            "parameters": {
                "type": "object",
                "properties": {
                    "data": {
                        "type": "string",
                        "description": "Data da reunião no formato DD/MM/AAAA. Vazio se o cliente disse só o horário.",
                    },
                    "horario": {
                        "type": "string",
                        "description": "Horário de início no formato HH:MM (24 h), por exemplo 14:00 ou 09:30.",
                    },
                },
                "required": ["data", "horario"],
                "additionalProperties": False,
            },
            "strict": True,
        },
        {
            "type": "function",
            "name": "oferecer_outros_horarios",
            "description": "O cliente só consegue num período (manhã, tarde ou noite) e/ou num dia, sem dizer o horário. Oferece outros horários livres dentro disso.",
            "parameters": {
                "type": "object",
                "properties": {
                    "periodo": {
                        "type": "string",
                        "description": "Período do dia que o cliente pediu.",
                        "enum": ["manha", "tarde", "noite", "qualquer"],
                    },
                    "data": {
                        "type": "string",
                        "description": "Dia que o cliente pediu, no formato DD/MM/AAAA. Vazio se ele não disse o dia.",
                    },
                },
                "required": ["periodo", "data"],
                "additionalProperties": False,
            },
            "strict": True,
        },
        {
            "type": "function",
            "name": "perguntar_horario",
            "description": "O cliente não consegue nos horários (ou no dia) oferecidos e não disse outro. Pergunta qual horário, ou qual dia e horário, fica melhor.",
            "parameters": {
                "type": "object",
                "properties": {
                    "motivo": {
                        "type": "string",
                        "description": "'horarios' se ele não consegue nesses horários; 'dia' se não consegue nesse dia.",
                        "enum": ["horarios", "dia"],
                    },
                },
                "required": ["motivo"],
                "additionalProperties": False,
            },
            "strict": True,
        },
        {
            "type": "function",
            "name": "humano",
            "description": "Passa a conversa para um atendente humano.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nome_cliente": {
                        "type": "string",
                        "description": "Nome do cliente.",
                    },
                    "motivo": {
                        "type": "string",
                        "description": "Por que o cliente precisa de um atendente.",
                    },
                },
                "required": ["nome_cliente", "motivo"],
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
        return MeetingAgent(
            agent_container=agent_container,
            tool_container=tool_container,
            message_repository=repository_container.message,
            ai_client=client_container.ai(),
        )

    def _prompt(self, customer: dict, now: datetime) -> str:
        doc = Customer.objects(id=customer.get("id")).first() if customer.get("id") else None
        slots = offered_slots(doc) if doc else []
        now_local = to_local(now)
        first = (customer.get("name") or "").split(" ")[0]
        return self.system_prompt.format(
            offered=_offered(slots, now),
            now=f"{WEEKDAYS[now_local.weekday()]}, {now_local:%d/%m/%Y %H:%M}",
            calendar=_calendar(now_local),
            customer_name="" if first.startswith("WhatsApp") else first,
        )

    async def execute(self, context: list, customer: dict) -> list[dict]:
        context = [{"role": "developer", "content": self._prompt(customer, datetime.utcnow())}, *context]

        response = self.ai.create_model_response(
            model=self.model,
            input=context,
            tools=self.tools,
            instructions=self.instructions,
        )
        logger.info("[MEETING AGENT] Resposta gerada pela IA: %s", to_json_dump(response.get("output", [])))

        is_tool_trigger, tools = self._is_tool_trigger(response=response)
        if is_tool_trigger:
            # Uma function por vez: duas ao mesmo tempo poderiam marcar e oferecer horário juntas.
            return await self._handle_tools(customer=customer, context=context, tools=tools[:1])

        return [{"role": "assistant", "content": self._extract_output_text(response)}]
