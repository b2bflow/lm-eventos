import requests
import os
import re
import time
import random
from utils.logger import logger, to_json_dump
from interfaces.clients.chat_interface import IChat


class ZAPIClient(IChat):
    def __init__(self):
        self._base_url = os.getenv("ZAPI_BASE_URL")
        self._instance_id = os.getenv("ZAPI_INSTANCE_ID")
        self._instance_token = os.getenv("ZAPI_INSTANCE_TOKEN")
        self._client_token = os.getenv("ZAPI_CLIENT_TOKEN")
        self._headers = {"Content-Type": "application/json"}
        self._after_send_hooks = []
        self._executing_hooks = False

    def after_send(self, event: str, hook: callable, *args, **hook_kwargs) -> None:
        normalized_args = tuple(args) if args else ()
        normalized_kwargs = dict(hook_kwargs) if hook_kwargs else {}

        self._after_send_hooks.append(
            {
                "event": event,
                "callable": hook,
                "args": normalized_args,
                "kwargs": normalized_kwargs,
            }
        )

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

    def clear_after_send_hooks(self, hooks: list[dict]) -> None:
        self._after_send_hooks = [h for h in self._after_send_hooks if h not in hooks]

    def _validate_message(self, message: str) -> bool:
        # Trata a mensagem
        message_clean = message.strip()

        # Verifica se a mensagem não está vazia
        if not message_clean:
            print("❌ Dados incompletos: A mensagem é obrigatória.")
            return False

        return True

    def _validate_cell_number(self, cell_number: str) -> bool:
        # Verifica se o celular não está vazio
        if not cell_number:
            logger.info(
                "[Z-API] ❌ Dados incompletos: O número de telefone é obrigatório. %s",
                cell_number,
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

                # Remove espaços extras
                sentence = sentence.strip()

                if sentence:
                    cleaned_sentences.append(sentence)

        return cleaned_sentences

    def set_instance(self, instance: str, instance_key: str) -> None:
        self._instance_id = instance
        self._instance_token = instance_key

    def is_valid_message(self, **kwargs) -> bool:
        phone = self.get_phone(**kwargs)

        if not phone:
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

    def get_message(self, **kwargs) -> str:
        if "text" in kwargs:
            return kwargs["text"]["message"]

        return "Olá, Tenho interesse e queria mais informações, por favor."

    def get_phone(self, **kwargs) -> str:
        return self._resolve_phone(kwargs.get("phone", "")) or ""

    def _get_audio_url(self, **kwargs) -> str:
        try:
            url: str = kwargs["audio"]["audioUrl"]

            if not url:
                raise KeyError(
                    f"[Z-API] Erro ao recuperar url do audio: {to_json_dump(kwargs)}"
                )

            return kwargs["audio"]["audioUrl"]
        except KeyError as e:
            logger.error("[Z-API] Erro ao recuperar url do audio: %s", to_json_dump(e))
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

    def send_message(self, phone: str, message: str) -> bool:
        if not self._validate_message(message) or not self._validate_cell_number(phone):
            logger.error(
                "[Z-API] Dados incompletos: mensagem: %s, telefone: %s", message, phone
            )
            return False

        url = f"{self._resolve_url()}/send-text"
        headers = {**self._headers, "Client-Token": self._client_token}
        payload = {"phone": self._resolve_phone(phone), "delayTyping": 3}

        last_exception = None

        try:
            for attempt in range(1, 4):
                try:
                    messages = self._resolve_message(message)
                    for index, msg in enumerate(messages):
                        if not msg:
                            continue

                        msg_clean = msg[:-1] if msg.endswith(".") else msg
                        payload["message"] = msg_clean

                        response = requests.post(url, json=payload, headers=headers)

                        logger.info(
                            "[Z-API] Enviando mensagem para %s: payload:\n%s \nresponse:%s",
                            phone,
                            to_json_dump(payload),
                            to_json_dump(response.json()),
                        )

                        response.raise_for_status()

                        lastMessage = len(messages) - 1
                        if index < lastMessage:
                            pause = random.randint(2, 3)
                            time.sleep(pause)
                    return True
                except Exception as e:
                    last_exception = e
                    logger.warning(
                        "[Z-API] Tentativa %d falhou ao enviar mensagem para %s: %s",
                        attempt,
                        phone,
                        e,
                    )
                    time.sleep(3)

            logger.error(
                "[Z-API] ❌ Todas as tentativas falharam ao enviar mensagem para %s",
                phone,
            )

            raise last_exception
        finally:
            self._execute_after_send_hooks(event="send_message")

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

    def send_document(
        self,
        phone: str,
        document: str,
        extension: str,
        file_name: str = None,
        caption: str = None,
    ) -> bool:
        if not self._validate_cell_number(phone):
            logger.error(
                "[Z-API] Dados incompletos telefone: %s",
                phone,
            )
            return False

        url = f"{self._resolve_url()}/send-document/{extension}"
        headers = {**self._headers, "Client-Token": self._client_token}
        payload = {
            "phone": self._resolve_phone(phone),
            "document": document,
            "delayTyping": 3,
        }

        if file_name:
            payload["fileName"] = file_name

        if caption:
            payload["caption"] = caption

        last_exception = None

        try:
            for attempt in range(1, 4):
                try:
                    payload["message"] = caption
                    response = requests.post(url, json=payload, headers=headers)
                    logger.info(
                        "[Z-API] Enviando documento para %s: %r \nresponse:%s",
                        phone,
                        caption,
                        to_json_dump(response.json()),
                    )
                    response.raise_for_status()

                    return True
                except Exception as e:
                    last_exception = e
                    logger.warning(
                        "[Z-API] Tentativa %d falhou ao enviar documento para %s: %s",
                        attempt,
                        phone,
                        e,
                    )
                    time.sleep(3)

            logger.error(
                "[Z-API] ❌ Todas as tentativas falharam ao enviar documento para %s",
                phone,
            )

            raise last_exception
        finally:
            self._execute_after_send_hooks(event="send_document")

    def send_image(self, phone: str, image: str, caption: str | None = None) -> bool:
        url = f"{self._resolve_url()}/send-image"
        headers = {**self._headers, "Client-Token": self._client_token}
        payload = {
            "phone": self._resolve_phone(phone),
            "image": image,
            "delayTyping": 3,
        }

        if caption:
            payload["caption"] = caption

        last_exception = None

        try:
            for attempt in range(1, 4):
                try:
                    response = requests.post(url, json=payload, headers=headers)

                    logger.info(
                        "[Z-API] Enviando imagem para %s: payload:\n%s \nresponse:%s",
                        phone,
                        to_json_dump(payload),
                        to_json_dump(response.json()),
                    )

                    response.raise_for_status()

                    return True
                except Exception as e:
                    last_exception = e
                    logger.warning(
                        "[Z-API] Tentativa %d falhou ao enviar imagem para %s: %s",
                        attempt,
                        phone,
                        e,
                    )
                    time.sleep(3)

            logger.error(
                "[Z-API] ❌ Todas as tentativas falharam ao enviar imagem para %s",
                phone,
            )

            raise last_exception
        finally:
            self._execute_after_send_hooks(event="send_image")

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

            logger.info("[Z-API] Tag criada: \n%s", to_json_dump(result))

            return result

        except Exception as e:
            logger.exception("[Z-API] ❌ Falha ao criar tag: \n%s", to_json_dump(e))
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

            logger.info("[Z-API] Lista de tags encontradas \n%s", to_json_dump(result))

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
            logger.exception("[Z-API] ❌ Falha ao buscar tags: \n%s", to_json_dump(e))
            raise e

    def assign_tag_to_chat(self, phone: str, tag_id: int) -> bool:
        logger.info("[Z-API] Atribuindo tag %d ao chat %s...", tag_id, phone)

        url = f"{self._resolve_url()}/chats/{phone}/tags/{tag_id}/add"

        headers = {**self._headers, "Client-Token": self._client_token}

        try:
            response = requests.put(url, headers=headers)
            response.raise_for_status()
            result: dict = response.json()

            logger.info(
                "[Z-API] Tag atribuída ao chat %s: \n%s", phone, to_json_dump(result)
            )

            return result.get("value", False)

        except Exception as e:
            logger.exception(
                "[Z-API] ❌ Falha ao atribuir tag ao chat %s: \n%s",
                phone,
                to_json_dump(e),
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
                "[Z-API] Tag removida do chat %s: \n%s", phone, to_json_dump(result)
            )

            return result.get("value", False)

        except Exception as e:
            logger.exception(
                "[Z-API] ❌ Falha ao remover tag do chat %s: \n%s",
                phone,
                to_json_dump(e),
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
                    "[Z-API] Metadados do chat %s: \n%s", phone, to_json_dump(result)
                )
                return result
            except Exception as e:
                logger.warning(
                    "[Z-API] Tentativa %d falhou ao buscar metadados do chat %s: %s",
                    attempt,
                    phone,
                    e,
                )
                time.sleep(3)

        logger.error(
            "[Z-API] ❌ Todas as tentativas falharam ao buscar metadados do chat %s",
            phone,
        )
        return {}
