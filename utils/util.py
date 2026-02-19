from flask import jsonify, request
from functools import wraps
import os
import jwt


def only_numbers(value: str) -> str:
    if not value:
        return value

    return "".join(filter(str.isdigit, value))


def format_phone(value: str) -> str:
    if not value:
        return value

    digits = only_numbers(value)

    if len(digits) == 11:
        return f"({digits[:2]}) {digits[2:7]}-{digits[7:]}"
    elif len(digits) == 10:
        return f"({digits[:2]}) {digits[2:6]}-{digits[6:]}"
    return value


def format_cpf(value: str) -> str:
    if not value:
        return value

    digits = only_numbers(value)

    if len(digits) == 11:
        return f"{digits[:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:]}"
    return value


def format_cnpj(value: str) -> str:
    if not value:
        return value

    digits = only_numbers(value)

    if len(digits) == 14:
        return f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:]}"
    return value


def format_date(value: str) -> str:
    if not value:
        return value

    try:
        year, month, day = map(int, value.split("-"))
        return f"{day:02d}/{month:02d}/{year:04d}"
    except ValueError:
        return value
    

def token_required(func):
    @wraps(func)
    def decorated(*args, **kwargs):
        service_token = request.headers.get('Service-Token')
        if not service_token:
            return jsonify({'message': 'Token de autorização ausente!'}), 401

        if service_token != os.getenv('SERVICE_TOKEN'):
            return jsonify({'message': 'Token de autorização inválido!'}), 401

        return func(*args, **kwargs)

    return decorated


def auth_required(func):
    @wraps(func)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        # 1. Verifica se o header existe
        if not auth_header:
            return jsonify({'message': 'Token de autorização ausente!'}), 401

        try:
            # 2. Separa o "Bearer" do token real
            # O split divide "Bearer eyJhb..." em duas partes
            scheme, token = auth_header.split()

            if scheme.lower() != 'bearer':
                return jsonify({'message': 'Formato inválido! Use: Bearer <token>'}), 401

        except ValueError:
            return jsonify({'message': 'Cabeçalho de autorização mal formatado!'}), 401

        # 3. Tenta validar o token com a biblioteca JWT
        try:
            # Pega a chave secreta do .env (mesma usada para gerar o token)
            secret_key = os.getenv('SECRET_KEY')

            # O decode valida a assinatura e se o token expirou
            decoded_data = jwt.decode(token, secret_key, algorithms=["HS256"])

            # [OPCIONAL MÁGICO]
            # Injetamos os dados decodificados (ex: id do usuário) dentro dos kwargs.
            # Assim, sua função da rota pode acessar quem é o usuário.
            kwargs['token'] = token
            kwargs['decoded_data'] = decoded_data

        except jwt.ExpiredSignatureError:
            return jsonify({'message': 'Token expirado! Faça login novamente.'}), 401

        except jwt.InvalidTokenError:
            return jsonify({'message': 'Token inválido!'}), 401

        return func(*args, **kwargs)

    return decorated
