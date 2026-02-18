from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime


class ISpreadsheet(ABC):

    SCHEDULED_STATUS = "Agendado"
    PRE_SCHEDULED_STATUS = "Pré-agendado"

    PLACES = [
        "Ranchinho",
        "Ranchão",
        "Churrasqueira 1",
        "Churrasqueira 2",
        "Churrasqueira 3",
        "Churrasqueira 4",
        "Churrasqueira 5",
        "Churrasqueira 6",
        "Churrasqueira 7",
        "Churrasqueira 8",
        "Churrasqueira 9",
    ]

    HEADERS = [
        "Criado em",
        "Nome completo",
        "Telefone",
        "Endereço",
        "Data pré-agendada",
        "Local pré-reservado",
        "Status",
    ]

    @abstractmethod
    def insert_row(
        self,
        name: str,
        phone: str,
        address: str,
        pre_reserved_date: str | datetime,
        pre_reserved_place: str,
        status: str = "Pré-reservado",
    ) -> int:
        """
        Insere uma nova linha ao final com os valores nos cabeçalhos:
        Nome completo, Endereço, Data, Local pré-reservado, Status
        Retorna o número da nova linha criada (1-based).
        """
        ...

    @abstractmethod
    def find_rows_by_scheduling_date(
        self, date_value: str | datetime
    ) -> list[tuple[int, dict[str, object]]]:
        """
        Busca a primeira linha cuja coluna 'Data' casa com a data informada.
        Retorna uma tupla (row_number, row_as_dict) ou None se não encontrar.
        - row_number: número da linha 1-based no Google Sheets.
        - row_as_dict: dicionário mapeando cabeçalhos -> valores.
        """
        ...

    @abstractmethod
    def find_rows_by_created_at(
        self, date_value: str | datetime
    ) -> list[tuple[int, dict[str, object]]]: ...

    @abstractmethod
    def find_rows_by_header(
        self, header_name: str, value
    ) -> list[tuple[int, dict[str, object]]]: ...

    @abstractmethod
    def delete_row(self, row_number: int) -> bool:
        """
        Apaga a linha informada (1-based) do sheet atual.
        Retorna True em caso de sucesso.
        """
        ...
