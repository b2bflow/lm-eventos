import os
import time
import io
import json
from openai import OpenAI, OpenAIError, NotGiven, NOT_GIVEN
from utils.logger import logger, to_json_dump
from interfaces.clients.ai_interface import IAI
from openai.types.audio import Transcription


class OpenIAClient(IAI):
    MAX_AUDIO_TRANSCRIBE_MB = int(os.getenv("OPENAI_MAX_AUDIO_TRANSCRIBE_MB"))

    def __init__(self):
        self.assistant_id = os.getenv("OPENAI_ASSISTANT_ID")
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.max_output_tokens = int(os.getenv("OPENAI_MAX_OUTPUT_TOKENS", "998"))

    def function_call_output(
        self,
        function_call_id: str,
        call_id: str,
        call_name: str,
        output: str,
        arguments: dict,
        model: str = "gpt-4.1-nano",
    ) -> tuple[list, dict]:
        logger.info(
            f"[OPENAI] Function call output. function_call_id: {function_call_id}, call_id: {call_id}, function_call_id: {function_call_id}, output: {output}"
        )

        try:
            input = [
                {
                    "type": "function_call",
                    "id": function_call_id,
                    "call_id": call_id,
                    "name": call_name,
                    "arguments": json.dumps(arguments),
                },
                {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": output,
                },
            ]

            response = self.client.responses.create(
                model=model,
                instructions="",
                input=input,
                temperature=0.5,
            )

            logger.info(
                f"[OPENAI] Resposta do Function call output com o function_call_id {function_call_id}, call_id: {call_id}: \n{to_json_dump(response.to_dict().get('output'))}"
            )

            return (input, response.to_dict())
        except Exception as e:
            logger.exception(
                f"[OPENAI] ❌ Erro ao fazer o function call output: \n{to_json_dump(e)}"
            )
            raise e

    def transcribe_audio(self, audio_bytes: str) -> str:
        try:
            logger.info("[OPENAI] Transcrevendo audio...")

            buf = io.BytesIO(audio_bytes)
            buf.name = "voice.ogg"
            buf.seek(0, io.SEEK_END)
            size = buf.tell()
            buf.seek(0)

            if size > (self.MAX_AUDIO_TRANSCRIBE_MB * 1024 * 1024):
                raise Exception(
                    f"[OPENAI] O tamanho do audio é maior que {self.MAX_AUDIO_TRANSCRIBE_MB}MB"
                )

            result: Transcription = self.client.audio.transcriptions.create(
                model="whisper-1", file=buf, language="pt"
            )

            logger.info(f"[OPENAI] Resultado da transcrição: \n{to_json_dump(result)}")

            return result.text
        except OpenAIError as e:
            logger.exception(
                f"[OPENAI] ❌ Erro ao transcrever audio: \n{to_json_dump(e)}"
            )
            raise e

    def create_model_response(
        self,
        model: str,
        input: str | list,
        tools: list | None = None,
        instructions: str | None = None,
    ) -> dict:
        if not input:
            input = []

        try:
            logger.info(
                f"[OPENAI] Gerando resposta com o modelo: {model}, último input: \n{to_json_dump(input[-1]) if isinstance(input, list) else input}"
            )

            response = self.client.responses.create(
                model=model,
                instructions=instructions,
                input=input,
                tools=tools,
                temperature=0.5,
                top_p=1.0,
                store=True,
            )

            return response.to_dict()
        except OpenAIError as e:
            logger.exception(
                f"[OPENAI] ❌ Erro ao criar resposta do modelo: \n{to_json_dump(e)}"
            )
            raise e
