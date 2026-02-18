from datetime import datetime, timedelta
import json
from dotenv import load_dotenv

load_dotenv()

from container.container import Container

container = Container()


def get_reservations_for_next_day() -> list[tuple[int, dict[str, object]]]:
    next_day = datetime.now() + timedelta(days=1)
    reservations = container.clients.spreadsheet.find_rows_by_scheduling_date(
        date_value=next_day
    )

    pre_schedule_status = container.clients.spreadsheet.PRE_SCHEDULED_STATUS
    only_pre_scheduled = [
        reservation
        for reservation in reservations
        if reservation[1].get("Status") == pre_schedule_status
    ]

    return only_pre_scheduled


def remove_reservation(row_number: int) -> None:
    container.clients.spreadsheet.delete_row(row_number=row_number)


def main() -> None:
    reservations = get_reservations_for_next_day()

    for reservation in reservations:
        remove_reservation(row_number=reservation[0])


if __name__ == "__main__":
    main()
