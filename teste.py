# import requests
# import os
# from os import getenv
# from dotenv import load_dotenv
# from datetime import datetime
# from datetime import date, timedelta
# load_dotenv()


# def remove_tag_from_chat(phone: str, tag: str) -> dict[str, bool]:
#     # https://api.z-api.io/instances/{{instanceId}}/token/{{instanceToken}}/chats/{phone}/tags/{tag}/add
#     # https://api.z-api.io/instances/SUA_INSTANCIA/token/SEU_TOKEN/chats/{phone}
#     response = requests.put(
#         f"{os.getenv('ZAPI_BASE_URL')}/instances/{os.getenv('ZAPI_INSTANCE_ID')}/token/{os.getenv('ZAPI_INSTANCE_TOKEN')}/chats/{phone}/tags/{tag}/remove",
#         headers={"Client-Token": os.getenv("ZAPI_CLIENT_TOKEN")},
#     )

#     response.raise_for_status()

#     return response.json()


# def get_chat_metadata(phone: str):
#     response = requests.get(
#         f"{os.getenv('ZAPI_BASE_URL')}/instances/{os.getenv('ZAPI_INSTANCE_ID')}/token/{os.getenv('ZAPI_INSTANCE_TOKEN')}/chats/{phone}",
#         headers={"Client-Token": os.getenv("ZAPI_CLIENT_TOKEN")},
#     )

#     response.raise_for_status()

#     return response.json()


# def get_tags():
#     response = requests.get(
#         f"{os.getenv('ZAPI_BASE_URL')}/instances/{os.getenv('ZAPI_INSTANCE_ID')}/token/{os.getenv('ZAPI_INSTANCE_TOKEN')}/tags",
#         headers={"Client-Token": os.getenv("ZAPI_CLIENT_TOKEN")},
#     )

#     response.raise_for_status()

#     return response.json()

# # print(add_tag_to_chat("5595991178067", "Humano"))
# print(remove_tag_from_chat(phone="5571981472898", tag=7))
# tags = get_chat_metadata("5571981472898").get("tags", [])

# print(tags)

# print(get_tags())

