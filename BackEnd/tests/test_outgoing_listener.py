def test_send_outgoing_listener_sends_through_zapi(zapi_outbox):
    from gateway.listeners import handle_send_outgoing_message
    handle_send_outgoing_message({"phone": "5562999990000", "content": "Bom dia"})
    assert zapi_outbox == [{"phone": "5562999990000", "message": "Bom dia"}]


def test_after_send_hooks_are_initialized():
    # send_contact chama _execute_after_send_hooks no finally; antes faltavam os atributos.
    from gateway.adapters.zapi_adapter import ZAPIClient
    ZAPIClient()._execute_after_send_hooks(event="send_contact")
