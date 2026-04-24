import requests
import os
import re
import time
import random
import emoji
from utils.logger import logger, to_json_dump
# Verificar se a interface está correta 
from gateway.interfaces.chat_interface import IChat
from dotenv import load_dotenv

load_dotenv()

class ZAPIClient(IChat):
    def __init__(self):
        self._base_url = os.getenv("ZAPI_BASE_URL")
        self._instance_id = os.getenv("ZAPI_INSTANCE_ID")
        self._instance_token = os.getenv("ZAPI_INSTANCE_TOKEN")
        self._client_token = os.getenv("ZAPI_CLIENT_TOKEN")
        self._headers = {"Content-Type": "application/json"}

    def __validate_message(self, message: str) -> bool:
        # Trata a mensagem
        message_clean = message.strip()

        # Verifica se a mensagem não está vazia
        if not message_clean:
            print("❌ Dados incompletos: A mensagem é obrigatória.")
            return False

        return True

    def __validate_cell_number(self, cell_number: str) -> bool:
        # Verifica se o celular não está vazio
        if not cell_number:
            logger.info(
                f"[Z-API] ❌ Dados incompletos: O número de telefone é obrigatório. {cell_number}"
            )
            return False

        # Trata o telefone
        cell_number_clean = cell_number.strip()

        # Remove caracteres não numéricos
        cell_number_clean = re.sub(r"[^0-9]", "", cell_number_clean)

        # Verifica tamanho mínimo (11 dígitos = DDD + Celular)
        if len(cell_number_clean) < 11:
            logger.info(
                f"[Z-API] Telefone inválido. O número de celular deve conter no mínimo 11 dígitos (com DDD): {cell_number_clean}"
            )
            return False

        # Verifica tamanho máximo (13 dígitos = 11DDI + DDD + Celular)
        if len(cell_number_clean) > 13:
            print(
                f"[Z-API] Telefone inválido. O número de celular deve conter no máximo 13 dígitos (com DDI e DDD): {cell_number_clean}"
            )
            return False

        return True

    def _resolve_phone(self, phone: str) -> str:
        # Coloca o número o prefixo 9 caso o número tenha 8 dígitos
        if len(phone[4:]) == 8:
            phone = f"{phone[:4]}9{phone[4:]}"

        # Adiciona o DDI 55 caso não tenha
        if not phone.startswith("55") and len(phone) == 11:
            return f"55{phone}"

        return phone

    def _resolve_message(self, message: str) -> list[str]:
        """
        Quebra uma mensagem longa em frases menores baseado em pontos finais e interrogações.

        Regras:
        - Quebra em ponto final seguido de espaço (remove o ponto)
        - Quebra em interrogação (mantém a interrogação)
        - Ignora pontos em abreviações e listas numeradas
        - Ignora pontos decimais
        - Ignora pontos de interrogação em URLs
        """
        abrevs = [
            "Av",
            "R",
            "Rua",
            "Dr",
            "Dra",
            "Sr",
            "Sra",
            "Prof",
            "Rod",
            "Tv",
            "Est",
            "Sta",
            "Sto",
            "Ltda",
            "S.A",
            "etc",
            "obs",
            "pg",
            "fls",
        ]

        # Protege URLs (substitui temporariamente pontos e interrogações em URLs)
        # Padrão que captura URLs completas incluindo parâmetros
        url_pattern = (
            r"(https?://[^\s]+|www\.[^\s]+|[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}[^\s]*)"
        )
        urls = re.findall(url_pattern, message)

        for i, url in enumerate(urls):
            # Substitui a URL inteira por um placeholder
            message = message.replace(url, f"<<URL{i}>>")

        # Protege abreviações comuns (substitui temporariamente o ponto)
        for ab in abrevs:
            message = re.sub(
                rf"\b{ab}\.", f"{ab}<<ABBREV>>", message, flags=re.IGNORECASE
            )

        # Protege marcadores de lista numerada (1. 2. 3. etc.)
        message = re.sub(r"\b(\d+)\.", r"\1<<LIST>>", message)

        # Protege números decimais (1.5, 2.75, etc.)
        message = re.sub(r"(\d+)\.(\d+)", r"\1<<DECIMAL>>\2", message)

        # Lista para armazenar as frases processadas
        sentences = []
        current_sentence = ""
        i = 0

        while i < len(message):
            char = message[i]
            current_sentence += char

            # Verifica se encontrou um ponto de interrogação
            if char == "?":
                # Quebra aqui (mantém a interrogação)
                sentences.append(current_sentence.strip())
                current_sentence = ""

            # Verifica se encontrou um ponto final
            elif char == "." and i + 1 < len(message):
                # Verifica se o próximo caractere é um espaço
                if message[i + 1].isspace():
                    # Remove o ponto final da frase atual
                    current_sentence = current_sentence[:-1].strip()
                    if current_sentence:
                        sentences.append(current_sentence)
                    current_sentence = ""

            i += 1

        # Adiciona a última frase se houver conteúdo restante
        if current_sentence.strip():
            sentences.append(current_sentence.strip())

        # Restaura os pontos protegidos e limpa frases vazias
        cleaned_sentences = []
        for sentence in sentences:
            if sentence:
                # Restaura URLs primeiro
                for i, url in enumerate(urls):
                    sentence = sentence.replace(f"<<URL{i}>>", url)

                # Restaura abreviações, listas e decimais
                sentence = sentence.replace("<<ABBREV>>", ".")
                sentence = sentence.replace("<<LIST>>", ".")
                sentence = sentence.replace("<<DECIMAL>>", ".")

                sentence = sentence.strip()

                if sentence:
                    cleaned_sentences.append(sentence)

        return cleaned_sentences

    def set_instance(self, instance: str, instance_key: str) -> None:
        self._instance_id = instance
        self._instance_token = instance_key

    def _is_emoji_only(self, message: str) -> bool:
        clean_text = message.strip().replace(" ", "")

        if not clean_text:
            return False

        result = emoji.replace_emoji(clean_text, replace='')

        return len(result) == 0

    def is_valid_message(self, **kwargs) -> bool:
        phone = self.get_phone(**kwargs)

        if not phone:
            return False

        if 'sticker' in kwargs:
            return False

        if self._is_emoji_only(self.get_message(**kwargs)):
            return False
        
        return not kwargs["isGroup"] and kwargs["status"] == "RECEIVED"

    def is_image(self, **kwargs) -> bool:
        return "image" in kwargs and kwargs["image"].get("imageUrl") is not None

    def is_audio_message(self, **kwargs) -> bool:
        return "audio" in kwargs

    def is_file(self, **kwargs) -> bool:
        return (
            "document" in kwargs and kwargs["document"].get("documentUrl") is not None
        )
    
    def is_button_response(self, **kwargs) -> bool:
        return 'buttonsResponseMessage' in kwargs

    def get_message(self, **kwargs) -> str:
        if "text" in kwargs:
            return kwargs["text"]["message"]

        return "Olá, Tenho interesse e queria mais informações, por favor."

    def send_message_with_button(self, phone: str, message: str, buttons: list) -> dict:
        url = f"{self._resolve_url()}/send-button-list"

        headers = {**self._headers, "Client-Token": self._client_token}

        payload = {
            "phone": self._resolve_phone(phone),
            "message": message,
            "buttonList": {
                "buttons": buttons,
            },
            "delayTyping": 3,
        }

        try:
            if not buttons:
                logger.error(f"[Z-API] Lista de botões vazia: {phone}")
                return

            response = requests.post(url, json=payload, headers=headers)
            response.raise_for_status()

            logger.info(
                f"[Z-API] Lista de botões enviada para {phone}: \n{to_json_dump(response.json())}"
            )

        except Exception as e:
            logger.exception(f"[Z-API] ❌ Erro ao enviar lista de botões: \n{to_json_dump(e)}")
            raise e

    def get_phone(self, **kwargs) -> str:
        return self._resolve_phone(kwargs.get("phone", "")) or ""

    def _get_audio_url(self, **kwargs) -> str:
        try:
            url: str = kwargs["audio"]["audioUrl"]

            if not url:
                raise KeyError(
                    f"[Z-API] Erro ao recuperar url do audio: \n{to_json_dump(kwargs)}"
                )

            return kwargs["audio"]["audioUrl"]
        except KeyError as e:
            logger.error(e)
            raise e

    def get_audio_bytes(self, **kwargs) -> str:
        url = self._get_audio_url(**kwargs)
        return requests.get(url, timeout=15).content

    def get_image_url(self, **kwargs) -> str:
        return kwargs.get("image", {}).get("imageUrl", "")

    def get_image_caption(self, **kwargs) -> str:
        return kwargs.get("image", {}).get(
            "caption",
            "interprete a imagem e responda o usuário conforme o contexto e a imagem enviada",
        )

    def get_file_url(self, **kwargs) -> str:
        return kwargs.get("document", {}).get("documentUrl", "")

    def get_file_caption(self, **kwargs) -> str:
        return kwargs.get("document", {}).get(
            "caption",
            "interprete o arquivo e responda o usuário conforme o contexto e o arquivo enviado",
        )

    def _resolve_url(self) -> str:
        return f"{self._base_url}/instances/{self._instance_id}/token/{self._instance_token}"
    
    def clear_after_send_hooks(self, hooks: list[dict]) -> None:
        self._after_send_hooks = [h for h in self._after_send_hooks if h not in hooks]
    
    def _execute_after_send_hooks(self, event: str) -> None:
        if self._executing_hooks:
            return

        self._executing_hooks = True

        try:
            hooks_to_execute = [
                h for h in self._after_send_hooks if h.get("event") == event
            ]

            for hook in hooks_to_execute:
                try:
                    hook["callable"](
                        *hook.get("args", ()), **(hook.get("kwargs") or {})
                    )
                except Exception:
                    logger.error(
                        "[Z-API] Erro ao executar hook após envio: %s",
                    )

            # Remove os hooks que foram executados
            self.clear_after_send_hooks(hooks_to_execute)

        finally:
            self._executing_hooks = False
    
    def send_contact(self, phone: str, name: str, contact_phone: str) -> dict:
        url = self._resolve_url() + "/send-contact"

        headers = {**self._headers, "Client-Token": self._client_token}

        payload = {
            "phone": self._resolve_phone(phone),
            "contactName": name,
            "contactPhone": self._resolve_phone(contact_phone),
            "delayTyping": 3,
        }

        try:
            response = requests.post(url, json=payload, headers=headers)
            response.raise_for_status()

            logger.info(
                "[Z-API] Contato enviado para %s: \n%s",
                phone,
                to_json_dump(response.json()),
            )

            return response.json()

        except Exception as e:
            logger.exception(
                "[Z-API] ❌ Falha ao enviar contato: \n%s", to_json_dump(e)
            )
            raise e

        finally:
            self._execute_after_send_hooks(event="send_contact")

    def send_message(self, phone: str, message: str) -> bool:
        if not self.__validate_message(message) or not self.__validate_cell_number(
            phone
        ):
            logger.error(
                f"[Z-API] Dados incompletos: mensagem: {message}, telefone: {phone}"
            )
            return False

        url = f"{self._resolve_url()}/send-text"
        headers = {**self._headers, "Client-Token": self._client_token}
        payload = {"phone": self._resolve_phone(phone), "delayTyping": 3}

        last_exception = None

        for attempt in range(1, 4):
            try:
                messages = self._resolve_message(message)
                for msg in messages:
                    if not msg:
                        continue
                    msg_clean = msg[:-1] if msg.endswith(".") else msg
                    payload["message"] = msg_clean
                    response = requests.post(url, json=payload, headers=headers)
                    logger.info(
                        f"[Z-API] Enviando mensagem para {phone}: {msg_clean!r} payload:\n{to_json_dump(payload)} \nresponse:{to_json_dump(response.json())}"
                    )
                    response.raise_for_status()
                    pause = random.randint(2, 3)
                    time.sleep(pause)
                return True
            except Exception as e:
                last_exception = e
                logger.warning(
                    f"[Z-API] Tentativa {attempt} falhou ao enviar mensagem para {phone}: {e}"
                )
                time.sleep(3)

        logger.error(
            f"[Z-API] ❌ Todas as tentativas falharam ao enviar mensagem para {phone}"
        )

        raise last_exception

    def send_button_list(self, phone: str, message: str, buttons: list) -> dict:
        url = self._resolve_url() + "/send-button-list"

        headers = {**self._headers, "Client-Token": self._client_token}

        payload = {
            "phone": self._resolve_phone(phone),
            "message": message,
            "buttonList": {
                "buttons": buttons,
            },
            "delayTyping": 3,
        }

        try:
            if not buttons:
                logger.error(f"[Z-API] Lista de botões vazia: {phone}")
                return

            response = requests.post(url, json=payload, headers=headers)
            response.raise_for_status()

            logger.info(
                f"[Z-API] Lista de botões enviada para {phone}: \n{to_json_dump(response.json())}"
            )

        except Exception as e:
            logger.exception(
                f"[Z-API] ❌ Falha ao enviar lista de botões: \n{to_json_dump(e)}"
            )
            raise e

    def get_name(self, **kwargs):
        return kwargs.get("chatName", "")

    def create_tag(self, name: str, color: int) -> dict:
        url = f"{self._resolve_url()}/business/create-tag"

        headers = {**self._headers, "Client-Token": self._client_token}

        payload = {
            "name": name,
            "color": color,
        }

        try:
            response = requests.post(url, json=payload, headers=headers)
            response.raise_for_status()
            result = response.json()

            logger.info(f"[Z-API] Tag criada: \n{to_json_dump(result)}")

            return result

        except Exception as e:
            logger.exception(f"[Z-API] ❌ Falha ao criar tag: \n{to_json_dump(e)}")
            raise e

    def get_tag(
        self, id: str | None = None, name: str | None = None
    ) -> list | dict | None:
        url = f"{self._resolve_url()}/tags"
        headers = {**self._headers, "Client-Token": self._client_token}

        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            result = response.json()

            logger.info(f"[Z-API] Lista de tags encontradas \n{to_json_dump(result)}")

            if id:
                return next(
                    (tag for tag in result if tag.get("id", "") == str(id)), None
                )

            if name:
                return next(
                    (
                        tag
                        for tag in result
                        if tag.get("name", "").lower() == name.lower()
                    ),
                    None,
                )

            return result

        except Exception as e:
            logger.exception(f"[Z-API] ❌ Falha ao buscar tags: \n{to_json_dump(e)}")
            raise e

    def assign_tag_to_chat(self, phone: str, tag_id: int) -> bool:
        logger.info(f"[Z-API] Atribuindo tag {tag_id} ao chat {phone}...")

        url = f"{self._resolve_url()}/chats/{phone}/tags/{tag_id}/add"

        headers = {**self._headers, "Client-Token": self._client_token}

        try:
            response = requests.put(url, headers=headers)
            response.raise_for_status()
            result: dict = response.json()

            logger.info(
                f"[Z-API] Tag atribuída ao chat {phone}: \n{to_json_dump(result)}"
            )

            return result.get("value", False)

        except Exception as e:
            logger.exception(
                f"[Z-API] ❌ Falha ao atribuir tag ao chat {phone}: \n{to_json_dump(e)}"
            )
            return False

    def remove_tag_from_chat(self, phone: str, tag_id: int) -> bool:
        url = f"{self._resolve_url()}/chats/{phone}/tags/{tag_id}/remove"

        headers = {**self._headers, "Client-Token": self._client_token}

        try:
            response = requests.put(url, headers=headers)
            response.raise_for_status()
            result: dict = response.json()

            logger.info(
                f"[Z-API] Tag removida do chat {phone}: \n{to_json_dump(result)}"
            )

            return result.get("value", False)

        except Exception as e:
            logger.exception(
                f"[Z-API] ❌ Falha ao remover tag do chat {phone}: \n{to_json_dump(e)}"
            )
            return False

    def get_chat_metadata(self, phone: str) -> dict:
        url = f"{self._resolve_url()}/chats/{phone}"
        headers = {**self._headers, "Client-Token": self._client_token}

        for attempt in range(1, 4):
            try:
                response = requests.get(url, headers=headers)
                response.raise_for_status()
                result: dict = response.json()
                logger.info(
                    f"[Z-API] Metadados do chat {phone}: \n{to_json_dump(result)}"
                )
                return result
            except Exception as e:
                logger.warning(
                    f"[Z-API] Tentativa {attempt} falhou ao buscar metadados do chat {phone}: {e}"
                )
                time.sleep(3)

        logger.error(
            f"[Z-API] ❌ Todas as tentativas falharam ao buscar metadados do chat {phone}"
        )
        return {}