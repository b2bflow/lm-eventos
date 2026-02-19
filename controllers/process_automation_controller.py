from services.automation_service import AutomationService

class ProcessController:
    def __init__(self, service: AutomationService):
        self.service = service

    def get_customers(self, payload: dict) -> tuple[dict, int]:
        customers = self.service.customer_list(payload)
        return customers

    def authenticate(self, **payload) -> tuple[dict, int]:
        # auth_token = self.service.authenticate(**payload)
        # if not auth_token:
        #     return {"error": "Invalid credentials."}

        # return auth_token

        return self.service.authenticate(**payload)

    def create_manager(self, **payload) -> tuple[dict, int]:
        manager = self.service.create_manager(**payload)
        if not manager:
            return {"error": "Password and re-password do not match."}

        return {"manager": manager}

    def toggle_automation(self, **payload) -> tuple[dict, int]:
        self.service.toggle_automation(**payload)
        return {"message": "Automation status updated successfully."}

    def logout(self, **payload) -> tuple[dict, int]:
        self.service.logout(**payload)
        return {"message": "Logout successful."}