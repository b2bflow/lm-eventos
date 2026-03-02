from os import getenv

from aiohttp import payload
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from flask_cors import CORS
from cron_tasks.follow_up_task import run_abandoned_conversation_follow_up
from utils.logger import logger, to_json_dump
from utils.util import auth_required, token_required

load_dotenv()

from container.container import Container

app = Flask(__name__)

CORS(app)

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
    

@token_required
@app.post("/run_cron_job")
def run_cron_job():
    try:
        logger.info("[ENDPOINT RUN CRON JOB] Cron job iniciado com sucesso")
        run_abandoned_conversation_follow_up(
            hours_absence=int(getenv("ABANDONED_CONVERSATION_HOURS", "5"))
        )

        return jsonify({"status": "ok"}), 200

    except Exception as err:
        logger.exception(
            f"[ENDPOINT RUN CRON JOB] Erro ao processar endpoint /run_cron_job: {err}"
        )

        return jsonify({"status": "error"}), 500

@app.get("/get_customers")
@token_required
@auth_required
def get_customer(**kwargs) -> tuple:
    try:
        payload = {}

        payload['auth_token'] = kwargs.get('token', '')
        payload['email'] = kwargs.get('decoded_data', '').get('email')

        return jsonify({
            "data": container.controllers.process_controller.get_customers(payload),
            "status": 'ok'
        }), 200
    except Exception as err:
        logger.exception(
            f"[ENDPOINT PAYMENT CONFIRMATION] Erro ao processar endpoint /payment_confirmation: {err}"
        )
        return jsonify({"status": "error"}), 400

@app.post("/authenticate")
@token_required
def authenticate() -> tuple:
    payload: dict = request.get_json(silent=True) or {}
    try:
        return container.controllers.process_controller.authenticate(**payload)
    except Exception as err:
        logger.exception(
            f"[ENDPOINT PAYMENT CONFIRMATION] Erro ao processar endpoint /payment_confirmation: {err}"
        )
        return jsonify({"status": "error"}), 500

@app.post("/create_manager")
@token_required
def create_manager() -> tuple:
    payload: dict = request.get_json(silent=True) or {}
    try:
        return jsonify({
            "message": container.controllers.process_controller.create_manager(**payload),
            "status": 201
        })
    except Exception as err:
        logger.exception(
            f"[ENDPOINT PAYMENT CONFIRMATION] Erro ao processar endpoint /payment_confirmation: {err}"
        )
        return jsonify({"status": "error"}), 400

@app.post("/control_automation")
@token_required
@auth_required
def control(**kwargs) -> tuple:
    payload: dict = request.get_json(silent=True) or {}

    print(payload)

    payload['auth_token'] = kwargs.get('token', '')
    payload['email'] = kwargs.get('decoded_data', '').get('email')
    try:
        return container.controllers.process_controller.toggle_automation(**payload)

    except Exception as err:
        logger.exception(
            f"[ENDPOINT CONTROL] Erro ao processar endpoint /control: {err}"
        )

        return jsonify({"status": "error"}), 400

@app.post("/logout")
@token_required
@auth_required
def logout(**kwargs) -> tuple:
    payload: dict = request.get_json(silent=True) or {}

    payload['auth_token'] = kwargs.get('token', '')
    payload['email'] = kwargs.get('decoded_data', '').get('email')
    try:
        return container.controllers.process_controller.logout(**payload)

    except Exception as err:
        logger.exception(
            f"[ENDPOINT LOGOUT] Erro ao processar endpoint /logout: {err}"
        )

        return jsonify({"status": "error"}), 400
    

@app.post("/form_webhook")
def form_webhook(**kwargs) -> tuple:

    payload: dict = request.get_json(silent=True) or {}

    try:
        return container.controllers.process_controller.form_webhook(**payload)

    except Exception as err:
        logger.exception(
            f"[ENDPOINT FORM WEBHOOK] Erro ao processar endpoint /form_webhook: {err}"
        )

        return jsonify({"status": "error"}), 400