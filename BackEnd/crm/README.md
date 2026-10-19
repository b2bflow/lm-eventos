# crm: funil comercial e qualificação de lead

## Serviços para a IA (`LeadQualificationService`)

Prontos para serem chamados pelas functions da Lis. **Nada aqui está ligado ao `ToolContainer`**:
o João pluga depois. Obtenha o serviço pelo container:

```python
from crm.container import CrmContainer

qualification = CrmContainer.get_lead_qualification_service()
```

Todos recebem o `id` do `Customer` (string), aceitam `user=None` (vindo da IA, a linha do tempo
registra como sistema) e devolvem o lead atualizado (`Customer.to_dict()`). Erros de regra sobem
como `ValueError` com mensagem em português, que pode ser devolvida à IA como saída da function.

| Método | O que faz |
|---|---|
| `start_lead(customer_id, product)` | `product` em `estrutura_porta`, `estrutura_montagem`, `corporativo`, `social`, `produto_unico`. Define o produto e coloca o lead em `NEW_LEAD`. Se o lead atual já foi encerrado (`CONTRACT_SIGNED` ou `LOST`), ele vai para o histórico do contato (`opportunities`) e começa um lead novo do zero. |
| `save_field(customer_id, field, value)` | Grava em `Customer.qualification[field]`. Espelha `nome`, `email`, `empresa`, `cargo`, `local`, `data_evento`, `publico`, `tipo_evento`, `tipo_celebracao` e `titulo_evento` nos campos que o CRM já usa. `"não sei"`, `None` ou vazio entra em `pending_fields`; um valor real tira o campo de lá. |
| `add_attachment(customer_id, url, kind="outro", name=None)` | `kind` em `rider`, `projeto`, `orcamento_concorrente`, `lista_pecas`, `outro`. |
| `qualify_lead(customer_id, pending_fields=None, needs_erica=False)` | Move para `QUALIFIED`, grava `qualified_at`, sinaliza `ligacao_pendente` (e `aguardando_erica`), cria a tarefa `ligar_15min` (fora do horário comercial, 9h do próximo dia útil) e avisa a SDR por WhatsApp. |
| `mark_human_operator(customer_id, reason)` | Marca `human_operator=True`, `owner=erica`, coloca a conversa em `OPERADOR` (`ai_active=False`, `needs_attention=True`), cancela tarefas da SDR e avisa a Erica com motivo e contato. |

Campos aceitos por `save_field`: `crm/services/lead_qualification_service.py`
(`COMMON_FIELDS` + `PRODUCT_FIELDS[produto]`), ou `GET /api/v1/crm/qualification/fields/`.

### Exemplo: function `salvar_dado` numa tool

```python
import asyncio
from crm.container import CrmContainer


class SalvarDadoTool:
    """Exemplo de tool no padrão de ai_agents/tools (execute recebe customer, arguments...)."""

    async def execute(self, function_call_id, call_id, call_name, customer, context, arguments):
        service = CrmContainer.get_lead_qualification_service()
        try:
            await asyncio.to_thread(
                service.save_field, customer["id"], arguments["campo"], arguments.get("valor")
            )
            output = "Dado salvo."
        except ValueError as e:
            output = f"Não foi possível salvar: {e}"
        # ... devolver function_call_output como as tools atuais fazem
```

Sugestões combinadas no documento de negócio: `resumo` chama `qualify_lead` ao final da
qualificação; `humano` chama `mark_human_operator`; cada agente chama `start_lead` com o
produto do fluxo. A `SummaryTool` atual continua gravando os campos do evento pelo
`CustomerRepository.update` e não muda a etapa.

## Endpoints (todos exigem JWT)

Qualificação (os mesmos métodos, para a SDR no card e para testes):

```
POST /api/v1/crm/customers/<id>/qualification/start/       {"product": "estrutura_porta"}
POST /api/v1/crm/customers/<id>/qualification/field/       {"field": "data_retirada", "value": "24/10/2026"}
POST /api/v1/crm/customers/<id>/qualification/attachment/  {"url": "...", "kind": "lista_pecas", "name": "foto.jpg"}
POST /api/v1/crm/customers/<id>/qualification/qualify/     {"pending_fields": ["forma_retirada"], "needs_erica": false}
POST /api/v1/crm/customers/<id>/human-operator/            {"reason": "Parceiro antigo"}
```

Card do funil:

```
POST /api/v1/crm/customers/<id>/stage/        {"stage": "LOST", "lost_reason": "preco"}
POST /api/v1/crm/customers/<id>/flags/        {"add": ["aguardando_cliente"], "remove": []}
POST /api/v1/crm/customers/<id>/next-action/  {"next_step": "Ligar", "next_action_at": "2026-10-20T13:00:00Z"}
POST /api/v1/crm/customers/<id>/notes/        {"text": "..."}
POST /api/v1/crm/customers/<id>/calls/        {"outcome": "atendeu", "notes": "..."}
GET  /api/v1/crm/customers/<id>/timeline/
GET  /api/v1/crm/customers/<id>/tasks/
GET  /api/v1/crm/funnel/?product=&owner=&flag=&search=&include_human=&stage=&offset=
GET  /api/v1/crm/meta/          listas de etapas, produtos, flags, motivos de perda...
GET  /api/v1/crm/tasks/         fila da SDR (pendentes, por prazo)
POST /api/v1/crm/tasks/<id>/done/
GET|PATCH /api/v1/crm/settings/ configuração LM (PATCH só admin)
GET|POST  /api/v1/crm/contacts/                 contatos (search, contact_type, owner, partner, page)
GET|PATCH /api/v1/crm/contacts/<id>/            contato + leads (atual e anteriores), propostas, anexos
POST      /api/v1/crm/contacts/<id>/new-lead/   {product}: lead novo (exige o atual encerrado)
GET       /api/v1/crm/contacts/<id>/timeline/?lead=<id|current>
POST      /api/v1/crm/contacts/import-partners/ CSV (multipart `file`; `dry_run`), só admin ou b2bflow
```

## Contato e leads

O `Customer` é o contato (telefone único; o mesmo celular com e sem o nono dígito é o mesmo
contato, ver `crm/phones.py`) e guarda o lead em andamento, que é o que funil, propostas,
tarefas, agenda e a IA usam. Quando um contato com lead encerrado abre outro lead, o anterior é
copiado para `opportunities` e as propostas e a linha do tempo dele recebem `opportunity_id`.
O card do funil mostra só o lead atual; a página Contatos mostra todos. O dashboard soma os
leads arquivados.

Parceiros (`human_operator`) ficam com a Erica: a conversa nova abre em `OPERADOR`, sem menu de
boas-vindas e sem IA, e o contato não entra na fila da SDR. A importação por CSV marca os
números como parceiro sem avisar a Erica um a um.

## Etapas

`NEW_LEAD` → `QUALIFIED` → `PROPOSAL_SENT` → `PROPOSAL_ACCEPTED` → `CONTRACT_SIGNED`, e `LOST`
(motivo obrigatório). Transições em `crm/domain.py`. Não há mais inferência de etapa por
`quoted_amount`/`notes`. Para migrar dados antigos (idempotente):

```bash
python manage.py migrate_lm_stages --dry-run
python manage.py migrate_lm_stages
```
