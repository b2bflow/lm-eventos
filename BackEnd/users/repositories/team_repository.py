from utils.logger import logger
from typing import List, Optional
from users.models.team_model import Team


class TeamRepository:
    @staticmethod
    def create_team(name: str, description: str = "") -> Team:
        team = Team(name=name, description=description)
        team.save()
        return team

    @staticmethod
    def get_all_teams() -> List[Team]:
        return list(Team.objects.all().order_by('-created_at'))

    @staticmethod
    def get_team_by_id(team_id: str) -> Optional[Team]:
        try:
            return Team.objects.get(id=team_id)
        except Exception:
            return None

    @staticmethod
    def get_team_by_name(name: str) -> Optional[Team]:
        return Team.objects(name=name).first()

    @staticmethod
    def update_team(team: Team) -> Team:
        team.save()
        return team
        
    @staticmethod
    def delete_team(team: Team) -> None:
        team.delete()