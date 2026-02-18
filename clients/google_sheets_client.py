import os
from datetime import datetime, date, timedelta
from google.oauth2 import service_account
from googleapiclient.discovery import build
from interfaces.clients.spreadsheet_interface import ISpreadsheet
from utils.logger import logger, to_json_dump
from utils.util import format_phone


class GoogleSheetsClient(ISpreadsheet):

    # Mapeamento de índices de coluna baseado nos cabeçalhos
    COLUMN_INDEXES = {header: idx for idx, header in enumerate(ISpreadsheet.HEADERS)}

    def __init__(self):
        self.spreadsheet_id = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID")
        self.sheet_name = os.getenv("GOOGLE_SHEETS_SHEET_NAME")
        self.credentials_file = os.getenv("GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE")
        if not self.spreadsheet_id or not self.sheet_name:
            raise ValueError(
                "Defina GOOGLE_SHEETS_SPREADSHEET_ID e GOOGLE_SHEETS_SHEET_NAME"
            )

        self.load_credentials()

    def load_credentials(self) -> None:
        scopes = [os.getenv("GOOGLE_SHEETS_SCOPE")]
        creds = service_account.Credentials.from_service_account_file(
            self.credentials_file, scopes=scopes
        )
        self.service = build("sheets", "v4", credentials=creds)
        self.sheet_id = self._resolve_sheet_id(self.sheet_name)
        self._apply_data_validations()

    def insert_row(
        self,
        name: str,
        phone: str,
        address: str,
        pre_reserved_date: str | datetime,
        pre_reserved_place: str,
        status: str = ISpreadsheet.PRE_SCHEDULED_STATUS,
    ) -> int:
        if status not in [
            ISpreadsheet.SCHEDULED_STATUS,
            ISpreadsheet.PRE_SCHEDULED_STATUS,
        ]:
            raise ValueError(
                f"Status inválido: {status}. Valores aceitos: {', '.join(sorted([ISpreadsheet.SCHEDULED_STATUS, ISpreadsheet.PRE_SCHEDULED_STATUS]))}"
            )

        created_at = datetime.now().strftime("%d/%m/%Y %H:%M")
        place = self._validate_place(pre_reserved_place)
        status = self._validate_status(status)
        pre_reserved_date_formatted = self._format_date_for_sheet(pre_reserved_date)
        phone_formatted = format_phone(
            phone[2:] if phone.startswith("55") and len(phone) > 11 else phone
        )

        # Construir linha baseado nos cabeçalhos definidos
        row_data = {
            "Criado em": created_at,
            "Nome completo": name,
            "Telefone": phone_formatted,
            "Endereço": address,
            "Data pré-agendada": pre_reserved_date_formatted,
            "Local pré-reservado": place,
            "Status": status,
        }

        # Montar valores na ordem dos cabeçalhos
        values = [[row_data.get(header, "") for header in self.HEADERS]]

        range_notation = f"{self.sheet_name}!A1:G1"
        body = {"values": values}
        try:
            result = (
                self.service.spreadsheets()
                .values()
                .append(
                    spreadsheetId=self.spreadsheet_id,
                    range=range_notation,
                    valueInputOption="USER_ENTERED",
                    insertDataOption="INSERT_ROWS",
                    body=body,
                )
                .execute()
            )
            updated_range = result.get("updates", {}).get("updatedRange", "")
            row_number = self._extract_row_from_a1(updated_range)

            # Reaplicar validações na nova linha inserida
            self._apply_validation_to_row(row_number)

            logger.info(
                f"[GOOGLE SHEETS] Linha inserida. Resultado: \n{to_json_dump(result)}"
            )
            return row_number
        except Exception as e:
            logger.exception(f"[GOOGLE SHEETS] Erro ao inserir linha: {e}")
            raise

    def find_rows_by_scheduling_date(
        self, date_value: str | datetime
    ) -> list[tuple[int, dict[str, object]]]:
        return self.find_rows_by_header(
            header_name="Data pré-agendada", value=date_value
        )

    def find_rows_by_created_at(
        self, date_value: str | datetime
    ) -> list[tuple[int, dict[str, object]]]:
        return self.find_rows_by_header(header_name="Criado em", value=date_value)

    def find_rows_by_header(
        self, header_name: str, value
    ) -> list[tuple[int, dict[str, object]]]:
        headers = self._get_headers()
        if not headers:
            return []

        col_index = self._find_column_index(headers, header_name)
        if col_index is None:
            return []

        rows = self._get_rows()

        # Normaliza o valor de busca de acordo com o tipo da coluna
        target = self._normalize_value(value, header_name)
        if target is None:
            return []

        rows_found = []
        # Varre de baixo para cima: últimas linhas primeiro (mais recentes)
        for i in range(len(rows) - 1, -1, -1):
            row = rows[i]
            row_number = i + 2  # offset por conta do cabeçalho

            # Normaliza o valor da célula para comparação
            cell_value = row[col_index] if col_index < len(row) else None
            normalized_cell = self._normalize_value(cell_value, header_name)

            if normalized_cell and normalized_cell == target:
                row_dict = {
                    headers[j]: (row[j] if j < len(row) else "")
                    for j in range(len(headers))
                }
                rows_found.append((row_number, row_dict))

        return rows_found

    def delete_row(self, row_number: int) -> bool:
        if row_number <= 1:
            raise ValueError("row_number deve ser >= 2 (linha 1 é cabeçalho)")
        requests = [
            {
                "deleteDimension": {
                    "range": {
                        "sheetId": self.sheet_id,
                        "dimension": "ROWS",
                        "startIndex": row_number - 1,
                        "endIndex": row_number,
                    }
                }
            }
        ]
        try:
            result = (
                self.service.spreadsheets()
                .batchUpdate(
                    spreadsheetId=self.spreadsheet_id, body={"requests": requests}
                )
                .execute()
            )
            logger.info(
                f"[GOOGLE SHEETS] Linha {row_number} deletada. Resultado: \n{to_json_dump(result)}"
            )
            return True
        except Exception as e:
            logger.exception(f"[GOOGLE SHEETS] Erro ao deletar linha {row_number}: {e}")
            raise

    def _resolve_sheet_id(self, name: str) -> int:
        meta = (
            self.service.spreadsheets().get(spreadsheetId=self.spreadsheet_id).execute()
        )
        for s in meta.get("sheets", []):
            props = s.get("properties", {})
            if props.get("title") == name:
                return int(props.get("sheetId"))
        raise ValueError(f"A aba '{name}' não foi encontrada no spreadsheet")

    def _get_headers(self) -> list[str]:
        resp = (
            self.service.spreadsheets()
            .values()
            .get(spreadsheetId=self.spreadsheet_id, range=f"{self.sheet_name}!1:1")
            .execute()
        )
        values = resp.get("values", [])
        return values[0] if values else []

    def _get_rows(self) -> list[list[str]]:
        resp = (
            self.service.spreadsheets()
            .values()
            .get(spreadsheetId=self.spreadsheet_id, range=f"{self.sheet_name}!A2:G")
            .execute()
        )
        return resp.get("values", [])

    def _find_column_index(self, headers: list[str], column_name: str) -> int | None:
        for i, h in enumerate(headers):
            if h.strip().lower() == column_name.strip().lower():
                return i
        return None

    def _format_date_for_sheet(self, value: str | datetime) -> str:
        """
        Formata uma data para ser exibida corretamente no Google Sheets.
        Retorna no formato "dd/mm/yyyy" como texto.
        """
        if isinstance(value, str):
            # Se já for string, tenta normalizar para garantir formato correto
            d = self._normalize_to_date(value)
            if d:
                return d.strftime("%d/%m/%Y")
            return str(value)

        if isinstance(value, datetime):
            return value.strftime("%d/%m/%Y")

        if isinstance(value, date):
            return value.strftime("%d/%m/%Y")

        # Fallback
        return str(value) if value else ""

    def _normalize_value(self, value: object, header_name: str | None = None) -> object:
        """
        Normaliza valores para comparação, considerando o tipo de dado da coluna.

        Args:
            value: Valor a ser normalizado
            header_name: Nome do cabeçalho para determinar o tipo esperado

        Returns:
            Valor normalizado para comparação
        """
        if value is None:
            return None

        # Colunas que esperam datas
        date_columns = {"Data pré-agendada", "Criado em"}

        # Se for uma coluna de data, tenta normalizar para date
        if header_name and header_name in date_columns:
            return self._normalize_to_date(value)

        # Para outros tipos, normaliza para string em lowercase para comparação case-insensitive
        if isinstance(value, str):
            return value.strip().lower()

        if isinstance(value, (int, float)):
            return str(value)

        if isinstance(value, (datetime, date)):
            return value.strftime("%d/%m/%Y").lower()

        return str(value).strip().lower() if value else None

    def _normalize_to_date(self, value: object) -> date | None:
        """
        Normaliza um valor para o tipo date.
        Usado especificamente para colunas de data.
        """
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if isinstance(value, (int, float)):
            base = date(1899, 12, 30)
            try:
                days = int(value)
                return base + timedelta(days=days)
            except Exception:
                return None
        if isinstance(value, str):
            value = value.strip()
            patterns = [
                "%Y-%m-%d",
                "%Y-%m-%d %H:%M",
                "%d/%m/%Y",
                "%d/%m/%Y %H:%M",
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%dT%H:%M:%SZ",
            ]
            for p in patterns:
                try:
                    return datetime.strptime(value, p).date()
                except Exception:
                    pass
        return None

    def _extract_row_from_a1(self, a1: str) -> int:
        # Ex.: "Sheet1!A5:E5" -> 5
        if not a1:
            return -1
        tail = a1.split("!")[-1]
        parts = tail.split(":")[0]
        num = "".join(ch for ch in parts if ch.isdigit())
        return int(num) if num.isdigit() else -1

    def _apply_validation_to_row(self, row_number: int) -> None:
        """Aplica validações de lista suspensa a uma linha específica."""
        try:
            place_col_index = self.COLUMN_INDEXES.get("Local pré-reservado", 5)
            status_col_index = self.COLUMN_INDEXES.get("Status", 6)

            place_values = list(self.PLACES)
            status_values = [self.PRE_SCHEDULED_STATUS, self.SCHEDULED_STATUS]

            def validation_request(col_index: int, values: list[str]):
                return {
                    "setDataValidation": {
                        "range": {
                            "sheetId": self.sheet_id,
                            "startRowIndex": row_number - 1,
                            "endRowIndex": row_number,
                            "startColumnIndex": col_index,
                            "endColumnIndex": col_index + 1,
                        },
                        "rule": {
                            "condition": {
                                "type": "ONE_OF_LIST",
                                "values": [{"userEnteredValue": v} for v in values],
                            },
                            "showCustomUi": True,
                            "strict": True,
                        },
                    }
                }

            requests = [
                validation_request(place_col_index, place_values),
                validation_request(status_col_index, status_values),
            ]

            self.service.spreadsheets().batchUpdate(
                spreadsheetId=self.spreadsheet_id, body={"requests": requests}
            ).execute()

            logger.info(f"[GOOGLE SHEETS] Validações aplicadas à linha {row_number}")
        except Exception as e:
            logger.warning(
                f"[GOOGLE SHEETS] Erro ao aplicar validações à linha {row_number}: {e}"
            )

    def _apply_data_validations(self) -> None:
        try:
            meta = (
                self.service.spreadsheets()
                .get(
                    spreadsheetId=self.spreadsheet_id, ranges=[], includeGridData=False
                )
                .execute()
            )
            sheet = next(
                (
                    s
                    for s in meta.get("sheets", [])
                    if s.get("properties", {}).get("sheetId") == self.sheet_id
                ),
                None,
            )
            if not sheet:
                return
            row_count = (
                sheet.get("properties", {})
                .get("gridProperties", {})
                .get("rowCount", 5000)
            )

            def validation_request(col_index: int, values: list[str]):
                return {
                    "setDataValidation": {
                        "range": {
                            "sheetId": self.sheet_id,
                            "startRowIndex": 1,
                            "endRowIndex": row_count,
                            "startColumnIndex": col_index,
                            "endColumnIndex": col_index + 1,
                        },
                        "rule": {
                            "condition": {
                                "type": "ONE_OF_LIST",
                                "values": [{"userEnteredValue": v} for v in values],
                            },
                            "showCustomUi": True,
                            "strict": True,
                        },
                    }
                }

            place_values = list(self.PLACES)
            status_values = [self.PRE_SCHEDULED_STATUS, self.SCHEDULED_STATUS]

            # Usar índices dinâmicos baseados nos cabeçalhos
            place_col_index = self.COLUMN_INDEXES.get("Local pré-reservado", 5)
            status_col_index = self.COLUMN_INDEXES.get("Status", 6)

            requests = [
                validation_request(place_col_index, place_values),
                validation_request(status_col_index, status_values),
            ]

            self.service.spreadsheets().batchUpdate(
                spreadsheetId=self.spreadsheet_id, body={"requests": requests}
            ).execute()
        except Exception:
            pass

    def _validate_place(self, place: str) -> str:
        candidate = (place or "").strip()
        # Comparação case-insensitive preservando forma canônica
        for p in self.PLACES:
            if p.lower() == candidate.lower():
                return p
        raise ValueError(
            f"Local pré-reservado inválido: {place}. Valores aceitos: {', '.join(sorted(self.PLACES))}"
        )

    def _validate_status(self, status: str) -> str:
        candidate = (status or "").strip()
        allowed = {self.PRE_SCHEDULED_STATUS, self.SCHEDULED_STATUS}
        for s in allowed:
            if s.lower() == candidate.lower():
                return s
        raise ValueError(
            f"Status inválido: {status}. Valores aceitos: {', '.join(sorted(allowed))}"
        )
