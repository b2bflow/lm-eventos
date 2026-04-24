import os
import sys
import django
import random
from datetime import datetime, timedelta

# 1. Inicializa o ambiente Django para permitir o uso do ORM fora do manage.py
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "nucleus.settings")
django.setup()

# 2. Agora podemos importar os modelos tranquilamente
from crm.models.custumer_model import Customer
from chat.models.conversation_model import ConversationModel
from utils.logger import logger


def run(count=50):
    now = datetime.utcnow()
    
    statuses = ['NEW_LEAD', 'RETURN', 'INACURRENCE']
    weights = [60, 30, 10] 

    print(f"[InjectData] Iniciando injeção de {count} conversas falsas...")

    criados = 0
    for i in range(count):
        days_ago = random.randint(0, 29)
        mock_date = now - timedelta(days=days_ago)
        
        status = random.choices(statuses, weights=weights)[0]
        phone = f"551199900{random.randint(1000, 9999)}"
        
        try:
            customer = Customer(
                name=f"Mock Paciente {i}", 
                phone=phone, 
                actual_status=status
            )
            customer.save()
            
            conv = ConversationModel(
                customer=customer,
                status='CLOSED',
                tag='OPERADOR',
                final_customer_status=status,
                created_at=mock_date,
                updated_at=mock_date
            )
            conv.save()
            criados += 1
            
        except Exception as e:
            logger.error(f"[InjectData] Erro ao injetar registro {i}: {e}")

    print(f"\nSucesso! {criados} pacientes e conversas injetados nos últimos 30 dias.")

if __name__ == "__main__":
    run(count=100)