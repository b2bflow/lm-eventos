from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from utils.logger import logger
from collections import defaultdict

from crm.container import CrmContainer

class DashboardRepository:
    @classmethod
    def get_metrics(self, start_date: Optional[str] = None, end_date: Optional[str] = None) -> Dict[str, Any]:
        try:
            end_dt = datetime.utcnow()
            start_dt = end_dt - timedelta(days=30)
            
            if start_date:
                start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            if end_date:
                end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1) - timedelta(seconds=1)

            quote_service = CrmContainer.get_quote_service()
            quotes = quote_service.list_quotes()
            total_leads_general = len(quotes)
            filtered_quotes = []
            upcoming_window_end = datetime.utcnow() + timedelta(days=30)
            occupied_dates = set()

            daily_stats = defaultdict(lambda: {
                "lead_pipeline": 0,
                "confirmed_events": 0,
                "projected_revenue": 0.0,
            })

            summary = {
                "analysis": 0,
                "budget": 0,
                "negotiating": 0,
                "won": 0,
                "lost": 0,
                "projected_revenue": 0.0,
                "confirmed_revenue": 0.0,
            }

            for quote in quotes:
                created_at_raw = quote.get("created_at")
                created_at = datetime.fromisoformat(created_at_raw) if isinstance(created_at_raw, str) else created_at_raw
                if not created_at or created_at < start_dt or created_at > end_dt:
                    continue

                filtered_quotes.append(quote)
                day_str = created_at.strftime("%d/%m")
                stage = quote.get("status") or quote.get("customer_state_now", "ANALYSIS")
                quoted_amount = float(quote.get("quoted_amount") or 0)
                contract_value = float(quote.get("contract_value") or 0)
                revenue_reference = contract_value or quoted_amount

                daily_stats[day_str]["lead_pipeline"] += 1
                daily_stats[day_str]["projected_revenue"] += revenue_reference

                if stage == "ANALYSIS":
                    summary["analysis"] += 1
                elif stage == "BUDGET":
                    summary["budget"] += 1
                elif stage == "NEGOTIATING":
                    summary["negotiating"] += 1
                elif stage == "WON":
                    summary["won"] += 1
                    daily_stats[day_str]["confirmed_events"] += 1
                    summary["confirmed_revenue"] += contract_value or quoted_amount
                elif stage == "LOST":
                    summary["lost"] += 1

                if stage != "LOST":
                    summary["projected_revenue"] += revenue_reference

                event_date_raw = quote.get("event_date")
                event_date = datetime.fromisoformat(event_date_raw) if isinstance(event_date_raw, str) and event_date_raw else event_date_raw
                if event_date and datetime.utcnow() <= event_date <= upcoming_window_end:
                    occupied_dates.add(event_date.date().isoformat())

            labels = []
            lead_pipeline_series = []
            confirmed_events_series = []
            projected_revenue_series = []

            current_dt = start_dt
            while current_dt <= end_dt:
                day_str = current_dt.strftime("%d/%m")
                labels.append(day_str)
                lead_pipeline_series.append(daily_stats[day_str]["lead_pipeline"])
                confirmed_events_series.append(daily_stats[day_str]["confirmed_events"])
                projected_revenue_series.append(round(daily_stats[day_str]["projected_revenue"], 2))
                current_dt += timedelta(days=1)

            total_leads = len(filtered_quotes)
            events_confirmed = summary["won"]
            conversion_rate = round((events_confirmed / total_leads) * 100, 2) if total_leads else 0
            interruption_count = max(total_leads - summary["negotiating"] - summary["won"], 0)
            interruption_rate = round((interruption_count / total_leads) * 100, 2) if total_leads else 0
            schedule_occupancy_rate = round((len(occupied_dates) / 30) * 100, 2)
            average_ticket = round((summary["confirmed_revenue"] / events_confirmed), 2) if events_confirmed else 0

            return {
                "labels": labels,
                "lead_pipeline_series": lead_pipeline_series,
                "confirmed_events_series": confirmed_events_series,
                "projected_revenue_series": projected_revenue_series,
                "total_leads_general": total_leads_general,
                "total_leads": total_leads,
                "analysis_count": summary["analysis"],
                "budget_count": summary["budget"],
                "negotiating_count": summary["negotiating"],
                "events_confirmed": events_confirmed,
                "lost_count": summary["lost"],
                "interruption_count": interruption_count,
                "projected_revenue": round(summary["projected_revenue"], 2),
                "confirmed_revenue": round(summary["confirmed_revenue"], 2),
                "conversion_rate": conversion_rate,
                "sales_conversion_rate": conversion_rate,
                "interruption_rate": interruption_rate,
                "schedule_occupancy_rate": schedule_occupancy_rate,
                "upcoming_events_count": len(occupied_dates),
                "average_ticket": average_ticket,
            }

        except Exception as e:
            logger.error(f"[DashboardRepository] Erro ao calcular métricas: {e}")
            raise e
