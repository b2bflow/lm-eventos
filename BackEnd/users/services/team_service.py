from utils.logger import logger
from typing import List, Dict, Any
from users.repositories.team_repository import TeamRepository
from users.repositories.user_repository import UserRepository


class TeamService:

    @staticmethod
    def create_team(data: dict) -> Any:

        name = data.get('name')
        description = data.get('description', '')
        
        if not name or len(name.strip()) < 3:
            logger.warning("[TeamService] Tentativa de criar equipa com nome inválido.")
            raise ValueError("O nome da equipa deve ter pelo menos 3 caracteres.")
            
        if TeamRepository.get_team_by_name(name):
            logger.warning(f"[TeamService] Equipa já existente: {name}")
            raise ValueError("Já existe uma equipa com este nome.")
            
        logger.info(f"[TeamService] Criando nova equipa: {name}")
        return TeamRepository.create_team(name, description)
        
    @staticmethod
    def get_all_teams() -> List[Dict[str, Any]]:
        try:
            teams = TeamRepository.get_all_teams()
            return [
                {
                    "id": str(t.id),
                    "name": t.name,
                    "description": t.description,
                    "members": t.members,
                    "created_at": t.created_at
                } for t in teams
            ]
        except Exception as e:
            logger.error(f"[TeamService] Erro ao listar equipas: {str(e)}")
            return []

    @staticmethod
    def manage_members(team_id: str, user_id: str, action: str) -> Any:

        try:
            team = TeamRepository.get_team_by_id(team_id)
            if not team:
                raise ValueError("Equipa não encontrada.")
                
            user = UserRepository.get_by_id(user_id)
            if not user:
                logger.error(f"[TeamService] Usuário {user_id} não encontrado para ação {action}.")
                raise ValueError("Usuário não encontrado no sistema.")
                
            str_user_id = str(user_id)
                
            if action == 'ADD':
                if str_user_id in team.members:
                    raise ValueError("O usuário já pertence a esta equipa.")
                team.members.append(str_user_id)
                logger.info(f"[TeamService] Usuário {user_id} adicionado à equipa {team.name}")
                
            elif action == 'REMOVE':
                if str_user_id not in team.members:
                    raise ValueError("O usuário não pertence a esta equipa.")
                team.members.remove(str_user_id)
                logger.info(f"[TeamService] Usuário {user_id} removido da equipa {team.name}")
                
            else:
                raise ValueError("Ação inválida. Use 'ADD' ou 'REMOVE'.")
                
            return TeamRepository.update_team(team)

        except ValueError as ve:
            raise ve
        except Exception as e:
            logger.error(f"[TeamService] Erro interno ao gerir membros da equipa {team_id}: {str(e)}")
            raise e