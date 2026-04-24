from utils.logger import logger
from typing import Optional, List
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.core.exceptions import ObjectDoesNotExist
from datetime import datetime, timedelta
from users.models import User as UserModel

# DIRETRIZ OMNI: Identificador de classe no logger
User = get_user_model()

class UserRepository:

    @classmethod
    def create_user(self, data: dict) -> Optional[UserModel]:
        try:
            with transaction.atomic():
                user = User.objects.create_user(
                    username=data.get('username'),
                    email=data.get('email'),
                    password=data.get('password'),
                    first_name=data.get('first_name', ''),
                    is_staff=data.get('is_staff', False),
                    is_active=data.get('is_active', True)
                )
            return user
        except IntegrityError as e:
            logger.warning(f"[UserRepository] Tentativa de cadastro duplicado: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"[UserRepository] Erro crítico ao criar usuário: {str(e)}", exc_info=True)
            raise e

    @classmethod
    def get_by_id(self, user_id: int | str) -> Optional[UserModel]:
        try:
            return User.objects.get(id=user_id)
        except (ObjectDoesNotExist, ValueError):
            return None
        except Exception as e:
            logger.error(f"[UserRepository] Erro ao buscar ID {user_id}: {str(e)}")
            return None

    @classmethod
    def get_active_users_filter_last_login(self, time_threshold) -> List[UserModel]:
        try:
            return list(User.objects.filter(
                is_active=True,
                last_login__gte=time_threshold
            ))
        except Exception as e:
            logger.error(f"[UserRepository] Erro no filtro de online: {str(e)}")
            return []

    @classmethod
    def update_last_login(self, user_id: int, timestamp) -> bool:
        try:
            User.objects.filter(pk=user_id).update(last_login=timestamp)
            return True
        except Exception as e:
            logger.error(f"[UserRepository] Erro ao atualizar last_login para ID {user_id}: {str(e)}")
            return False
        
    @classmethod
    def set_user_offline(self, user_id: int) -> bool:
        try:
            past_time = datetime.utcnow() - timedelta(days=1)
            User.objects.filter(pk=user_id).update(last_login=past_time)
            return True
        except Exception as e:
            logger.error(f"[UserRepository] Erro ao definir offline para ID {user_id}: {str(e)}")
            return False
        
    @classmethod
    def update_user_profile(self, user_id: int, data: dict) -> Optional[UserModel]:
        try:
            user = self.get_by_id(user_id)
            if not user:
                return None
            
            if 'first_name' in data:
                user.first_name = data['first_name']
            if 'email' in data:
                user.email = data['email']
                
            user.save()
            return user
        except Exception as e:
            logger.error(f"[UserRepository] Erro ao atualizar perfil do ID {user_id}: {str(e)}")
            raise e

    @classmethod
    def update_password(self, user_id: int, new_password: str) -> bool:
        try:
            user = self.get_by_id(user_id)
            if not user:
                return False
            
            user.set_password(new_password)
            user.save()
            return True
        except Exception as e:
            logger.error(f"[UserRepository] Erro ao atualizar senha do ID {user_id}: {str(e)}")
            raise e
        
    @classmethod
    def get_all_users(self) -> List[UserModel]:
        try:
            return list(User.objects.all().order_by('-date_joined'))
        except Exception as e:
            logger.error(f"[UserRepository] Erro ao listar todos os usuários: {str(e)}")
            return []

    @classmethod
    def update_user_access(self, user_id: int, is_staff: bool = None, is_active: bool = None) -> Optional[UserModel]:
        try:
            user = self.get_by_id(user_id)
            if not user:
                return None
            
            if is_staff is not None:
                user.is_staff = is_staff
            if is_active is not None:
                user.is_active = is_active
                
            user.save()
            return user
        except Exception as e:
            logger.error(f"[UserRepository] Erro ao atualizar acesso do ID {user_id}: {str(e)}")
            raise e