from utils.logger import logger


class SummaryMixin:
    _system_prompt_summary = """
        ## 📝 Prompt para Resumo de CRM (Responda SOMENTE com o resumo)

A partir da conversa, gere um **resumo objetivo** contendo **exclusivamente as informações fornecidas pelo usuário**, sem saudações ou frases adicionais, Não inclua as menssagens nem dousuário, nem da IA.

### Os seguintes itens devem ser incluídos sempre que o usuário os informar:
- Nome do cliente
- Motivo da procura / intenção
- Se o serviço é apenas para ele ou para mais pessoas
- Endereço completo ou parcial informado
- Quaisquer outros dados relevantes fornecidos pelo usuário

### Regras Obrigatórias
- **A resposta deve conter somente o resumo.**
- **Não escreva cumprimentos, explicações ou frases adicionais.**
- **Não escreva textos introdutórios ou conclusões.**
- **Não inclua nada que tenha sido dito pela IA — apenas informações do usuário.**
- **Considere apenas o que foi dito pelo usuário.**

### Formato Obrigatório da Resposta
IMPORTANTE: A resposta deve ser **exatamente assim**, sem qualquer conteúdo antes ou depois:
    - Nome: [...]
    - Motivo da procura: [...]
    - Serviço para: [...]
    - Endereço: [...]
    - Observações adicionais: [informações diversas, e os cpf dos dependentes se houver]
"""
    # _system_prompt_summary = "Gere um resumo somente das mensagens do usuário para o CRM com as principais informações da conversa. Responda apenas com o conteúdo do resumo, sem saudações ou frases adicionais."

    def _check_requirements_summary(self) -> None:
        if not hasattr(self, "_extract_output_text"):
            raise AttributeError(
                "A classe deve possuir o método '_extract_output_text' para usar CreateSummaryMixin"
            )

        if not hasattr(self, "ai"):
            raise AttributeError(
                "A classe deve possuir a implementação da 'AI' para usar SummaryMixin"
            )

        if not hasattr(self, "crm"):
            raise AttributeError(
                "A classe deve possuir a implementação do 'CRM' para usar SummaryMixin"
            )

    def _create_summary(self, context: list, model: str) -> str:
        self._check_requirements_summary()

        system_prompt = {"role": "system", "content": self._system_prompt_summary}

        logger.info(f"[SUMMARY MIXIN] Contexto sem system prompt: {context}")

        logger.info(f"[SUMMARY MIXIN] System prompt: {system_prompt}")

        # context[1:].insert(0, system_prompt)

        context_with_system_prompt = context

        logger.info(f"[SUMMARY MIXIN] Contexto com system prompt: {context_with_system_prompt}")

        summary_response = self.ai.create_model_response(
            model=model,
            input=str(context),
            instructions=str(self._system_prompt_summary),
        )

        return self._extract_output_text(summary_response)

    def _create_and_register_summary_in_crm(
        self,
        context: list,
        model: str,
        deal_id: str | None = None,
        person_id: str | None = None,
    ) -> None:
        self._check_requirements_summary()

        summary = self._create_summary(
            context=context,
            model=model,
        )

        self.crm.create_history(
            message=summary,
            person_id=person_id,
            deal_id=deal_id,
        )
