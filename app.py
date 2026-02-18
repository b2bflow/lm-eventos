from dotenv import load_dotenv
from flask import Flask, request, jsonify
from utils.logger import logger, to_json_dump

load_dotenv()

from container.container import Container

app = Flask(__name__)
container = Container()


@app.route("/message_receive", methods=["POST"])
def receive_message() -> tuple:
    payload: dict = request.get_json(silent=True) or {}

    logger.info(
        f"[ENDPOINT RECEIVE MESSAGE] Requisição recebida: \n{to_json_dump(payload)}"
    )

    try:
        return container.controllers.process_incoming_message_controller.handle(
            **payload
        )

    except Exception as err:
        logger.exception(
            f"[ENDPOINT RECEIVE MESSAGE] Erro ao processar endpoint /receive_message: {err}"
        )

        return jsonify({"status": "error"}), 400
