import os
import jwt
from flask import jsonify
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash
from interfaces.repositories.customer_repository_interface import ICustomerRepository
from interfaces.repositories.manager_repository_interface import IManagerRepository
from interfaces.clients.chat_interface import IChat
from utils.logger import logger


load_dotenv()

class AutomationService:
    def __init__(self, customer_repository: ICustomerRepository, manager_repository: IManagerRepository, chat_client: IChat) -> None:
        self.customer_repository = customer_repository
        self.manager_repository = manager_repository
        self.chat = chat_client

    def customer_list(self, payload: dict) -> list:

        email = payload.get("email")
        auth_token = payload.get("auth_token")

        manager = self.manager_repository.find(email=email)

        if not manager:
            return None

        if not manager.get("session_token") == auth_token:
            return None

        return self.customer_repository.get_all_customers()

    def toggle_automation(self, **payload) -> None:
        customer_id = payload.get("id")
        toggle = payload.get("active")
        email = payload.get("email")
        auth_token = payload.get("auth_token")

        manager = self.manager_repository.find(email=email)

        if not manager:
            return None

        if not manager.get("session_token") == auth_token:
            return None
        
        print("passou")

        self.customer_repository.update(
            id=customer_id,
            attributes={"automation": toggle},
        )

    def authenticate(self, **payload) -> dict | None:
        email = payload.get("email")
        password = payload.get("password")

        manager = self.manager_repository.find(email=email)

        if not manager:
            return jsonify({
                "status": "error",
                "message": "Usuário não encontrado"
            }), 400


        stored_hash = manager.get("password_hash")
        if not check_password_hash(stored_hash, password):
            return jsonify({
                "status": "error",
                "message": "Senha incorreta"
            }), 400



        auth_token = jwt.encode({"email": email}, os.getenv("SECRET_KEY"), algorithm="HS256")
        self.manager_repository.update(email=email, attributes={"session_token": auth_token})
        return jsonify({
            "status": "ok",
            "auth_token": auth_token
        }), 200

    def create_manager(self, **payload) -> dict:
        name = payload.get("name")
        email = payload.get("email")
        password = payload.get("password")
        re_password = payload.get("re_password")

        manager = self.manager_repository.find(email=email)
        if manager:
            return None

        if password != re_password:
            return None

        password_hash = generate_password_hash(password)

        return self.manager_repository.create(
            name=name,
            email=email,
            password_hash=password_hash,
        )

    def update(self, **payload):
        email = payload.get("email")
        attributes = payload.get("attributes")

        return self.manager_repository.update(email=email, attributes=attributes)

    def logout(self, **payload) -> None:
        email = payload.get("email")
        auth_token = payload.get("auth_token")

        manager = self.manager_repository.find(email=email)

        if not manager:
            return None

        if not manager.get("session_token") == auth_token:
            return None

        self.manager_repository.update(email=email, attributes={"session_token": None})

    def form_webhook(self, **payload) -> dict:

        print(payload)
        customer_name = payload.get("nome_cliente")

        try:
            phone = os.getenv("ADM_PHONE")
            message = f"Novo formulário recebido Cliente: {customer_name}\n\nSolicita-se verificação e andamento para orçamento"

            self.chat.send_message(
                phone=phone,
                message=message,
            )

            return jsonify({"status": "ok"}), 200

        except Exception as err:
            logger.exception(
                f"[AUTOMATION SERVICE] Erro ao enviar mensagem no form_webhook: {err}"
            )
            return jsonify({"status": "error"}), 500