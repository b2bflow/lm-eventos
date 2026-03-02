from dotenv import load_dotenv

load_dotenv()

from container.container import Container
from os import getenv
from utils.logger import logger, to_json_dump
from datetime import datetime
from zoneinfo import ZoneInfo

container = Container()


def get_follow_up_message(customer: dict) -> str:
    return f"Olá! 😊\n\nNotamos que faz algum tempo desde sua última mensagem. Caso ainda precise de ajuda ou queira continuar a conversa, estamos à disposição para ajudar você"


def send_follow_up_message(phone: str, message: str) -> None:
    container.clients.chat.send_message(
        phone=phone,
        message=message,
    )


def mark_follow_up_as_done(customer_id: str) -> None:
    container.repositories.customer.update(
        id=customer_id, attributes={"follow_up_done": True}
    )

def mark_follow_up_as_pending(customer_id: str) -> None:
    container.repositories.customer.update(
        id=customer_id, attributes={"follow_up_done": False}
    )

def is_business_hours():
    tz_brasilia = ZoneInfo("America/Sao_Paulo")
    agora = datetime.now(tz_brasilia)
    
    is_weekday = agora.weekday() < 5 
    
    is_within_time = 9 <= agora.hour < 18
    
    return is_weekday and is_within_time

def run_abandoned_conversation_follow_up(hours_absence: int):
    if not is_business_hours():
        logger.info("[FOLLOW-UP TASK] Fora do horário comercial (09h-18h). Tarefa abortada.")
        return

    try:
        abandoned_conversations = (
            container.services.follow_up_service.get_abandoned_conversations(
                hours_absence=hours_absence
            )
        )

        logger.info(
            f"[FOLLOW-UP TASK] {len(abandoned_conversations)} conversas abandonadas para follow-up"
        )

        for customer in abandoned_conversations:
            send_follow_up_message(
                phone=customer.get("phone"),
                message=get_follow_up_message(customer=customer),
            )

            mark_follow_up_as_done(customer.get("id"))

            logger.info(
                "[FOLLOW-UP TASK] Follow-up enviado para customer: %s",
                customer.get("phone"),
            )

        logger.info("[FOLLOW-UP TASK] Follow-up concluído com sucesso ✅")
    except Exception as e:
        logger.error(f"[FOLLOW-UP TASK] Erro ao processar follow-up: {e}")


if __name__ == "__main__":
    run_abandoned_conversation_follow_up(
        hours_absence=int(getenv("ABANDONED_CONVERSATION_HOURS", "5"))
    )
