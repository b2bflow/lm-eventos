import os
from ai_agents.containers.repository_container import RepositoryContainer
from ai_agents.containers.tool_container import ToolContainer
from ai_agents.containers.agent_container import AgentContainer
from ai_agents.containers.client_container import ClientContainer
from chat.container import ChatContainer
from utils.logger import logger
from ai_agents.clients.openai_client import OpenIAClient
from ai_agents.interfaces.ai_interface import IAI
# from ai_agents.tools.final_tool import FinalTool
from ai_agents.agents.orchestrator import ResponseOrchestrator
from ai_agents.services.generate_response_service import GenerateResponseService


class AgentsContainer:
    _orchestrator = None
    _client = ClientContainer

    @classmethod
    def get_ai_client(self) -> _client.ai:
        logger.warning("<<<<<<<<<<<<<<<<<< aqui 1.2 >>>>>>>>>>>>>>>>>")
        try:
            logger.warning("[AiAgentsContainer] Tentando obter OPENAI_API_KEY do SystemConfigService.")
            api_key = os.getenv('OPENAI_API_KEY')

            if not api_key:
                logger.warning("[AiAgentsContainer] OPENAI_API_KEY não configurada no banco de dados! Usando fallback do .env")
                api_key = os.environ.get("OPENAI_API_KEY", "")

            return OpenIAClient(api_key=api_key)

        except Exception as e:
            logger.error(f"[AiAgentsContainer] Erro ao instanciar AI Client: {e}")
            raise e

    @classmethod
    def get_tools(self) -> list:
        return [
            FinalTool()
        ]

    @classmethod
    def get_Attendant_agent(self) -> ResponseOrchestrator:
        return ResponseOrchestrator(ai_client=self.get_ai_client(), tools=self.get_tools())

    @classmethod
    def get_orchestrator(self) -> GenerateResponseService:
        try:
            if not self._orchestrator:
                # 1. Montamos a sua nova árvore de dependências limpa
                clients = ClientContainer()
                repositories = RepositoryContainer(clients=clients)
                agent_container = AgentContainer(clients=clients, repositories=repositories, tools=None)

                tools = ToolContainer(clients=clients, repositories=repositories, agents=agent_container)
                agent_container.set_tools(tools)

                # 2. Injetamos o agent_container (Antes você estava passando 'self')
                self._orchestrator = GenerateResponseService(
                    chat_client=clients.chat(), # Tire os () se você manteve como @property no ClientContainer
                    message_repository=repositories.message, # Sem () porque no seu código é uma @property
                    customer_repository=repositories.customer, # Sem () porque no seu código é uma @property
                    agents=agent_container, # A MÁGICA ACONTECE AQUI!

                    conversation_repository=repositories.conversation,

                    # message_service=ChatContainer.message_service  # Acessando o MessageService via ChatContainer

                )
                logger.info("[AiAgentsContainer] AiOrchestratorService instanciado.")
            return self._orchestrator
        except Exception as e:
            logger.error(f"Erro ao instanciar o orchestrator: {e}")
            raise e