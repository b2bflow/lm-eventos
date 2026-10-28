import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { ArchiveRestore, Boxes, CalendarClock, ClipboardCheck, Loader2, Minus, Plus, Trash2 } from "lucide-react";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import api from "@/services/api";
import { cn } from "@/lib/utils";
import { formatBRL, formatDateTime, formatDay } from "@/lib/format";
import { useInventoryItem, type InventoryItemDetail, type InventoryReservation } from "@/hooks/useSales";
import { BILLING_UNITS, INVENTORY_LINES } from "./constants";


const today = () => new Date().toISOString().slice(0, 10);

/** Fim da reserva é gravado exclusivo (dia seguinte): mostra o último dia de uso. */
function lastDay(end: string) {
  const d = new Date(`${end.slice(0, 10)}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() - 1);
  return formatDay(d.toISOString());
}

function errorDetail(error: unknown, fallback: string) {
  return (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail || fallback;
}

function Section({ title, children, action }: { title: string; children: React.ReactNode; action?: React.ReactNode }) {
  return (
    <section className="space-y-2">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">{title}</h3>
        {action}
      </div>
      {children}
    </section>
  );
}

// Tamanho e descrição saíram da tela (o nome já diz o tamanho); continuam gravados no item.
type ItemForm = { name: string; line: string; billing_unit: string; owned: boolean };

const toForm = (item: InventoryItemDetail): ItemForm => ({
  name: item.name, line: item.line, billing_unit: item.billing_unit, owned: item.owned,
});

function DetailsSection({ item, canEdit, onSaved }: { item: InventoryItemDetail; canEdit: boolean; onSaved: () => void }) {
  const [form, setForm] = useState<ItemForm>(toForm(item));
  const [saving, setSaving] = useState(false);
  useEffect(() => setForm(toForm(item)), [item]);
  const dirty = JSON.stringify(form) !== JSON.stringify(toForm(item));

  const save = async () => {
    if (!form.name.trim()) return toast.error("Informe o nome.");
    setSaving(true);
    try {
      await api.patch(`/inventory/items/${item.id}/`, form);
      toast.success("Item atualizado.");
      onSaved();
    } catch (e) {
      toast.error(errorDetail(e, "Não foi possível salvar."));
    } finally {
      setSaving(false);
    }
  };

  if (!canEdit) {
    return (
      <Section title="Detalhes">
        <dl className="grid grid-cols-2 gap-2 text-sm">
          <dt className="text-muted-foreground">Linha</dt><dd>{item.line}</dd>
          <dt className="text-muted-foreground">Cobrança</dt><dd>{item.billing_unit}</dd>
          <dt className="text-muted-foreground">Origem</dt><dd>{item.owned ? "próprio" : "terceirizado"}</dd>
        </dl>
      </Section>
    );
  }

  return (
    <Section title="Detalhes">
      <div className="space-y-3">
        <div className="space-y-1">
          <Label className="text-xs">Nome</Label>
          <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1">
            <Label className="text-xs">Linha</Label>
            <Select value={form.line} onValueChange={(line) => setForm({ ...form, line })}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>{INVENTORY_LINES.map((l) => <SelectItem key={l} value={l}>{l}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label className="text-xs">Cobrança por</Label>
            <Select value={form.billing_unit} onValueChange={(billing_unit) => setForm({ ...form, billing_unit })}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>{BILLING_UNITS.map((u) => <SelectItem key={u} value={u}>{u}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <label className="flex items-center gap-2 text-sm pt-5">
            <Switch checked={!form.owned} onCheckedChange={(v) => setForm({ ...form, owned: !v })} />
            Terceirizado
          </label>
        </div>
        {dirty && (
          <div className="flex justify-end gap-2">
            <Button size="sm" variant="ghost" onClick={() => setForm(toForm(item))}>Descartar</Button>
            <Button size="sm" onClick={save} disabled={saving}>{saving && <Loader2 className="w-4 h-4 animate-spin" />}Salvar</Button>
          </div>
        )}
      </div>
    </Section>
  );
}

/** Preço de venda: grava na tabela de preços (o mesmo que a calculadora usa). Só a Erica (admin) edita. */
function PriceSection({ item, canEdit, onSaved }: { item: InventoryItemDetail; canEdit: boolean; onSaved: () => void }) {
  const [value, setValue] = useState("");
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const unit = item.billing_unit === "metro" ? "peça" : item.billing_unit;

  const save = async (price: string | null) => {
    setSaving(true);
    try {
      await api.patch(`/inventory/items/${item.id}/`, { sale_price: price });
      toast.success(price === null ? "Preço removido." : "Preço salvo.");
      setEditing(false);
      onSaved();
    } catch (e) {
      toast.error(errorDetail(e, "Não foi possível salvar o preço."));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Section title="Preço de venda">
      {editing ? (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm text-muted-foreground">R$</span>
          <Input autoFocus inputMode="decimal" className="w-32" value={value} placeholder="0,00"
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && value.trim()) save(value);
              if (e.key === "Escape") setEditing(false);
            }} />
          <span className="text-sm text-muted-foreground">por {unit}</span>
          <Button size="sm" onClick={() => save(value)} disabled={saving || !value.trim()}>
            {saving && <Loader2 className="w-4 h-4 animate-spin" />}Salvar
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setEditing(false)}>Cancelar</Button>
        </div>
      ) : (
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-sm">
            {item.sale_price === null
              ? <span className="text-amber-700 dark:text-amber-400">Sem preço: trava a proposta até ter preço.</span>
              : <><span className="text-lg font-semibold tabular-nums">{formatBRL(item.sale_price)}</span> <span className="text-muted-foreground">por {unit}</span></>}
          </p>
          {canEdit && (
            <div className="flex gap-1">
              {item.sale_price !== null && (
                <Button size="sm" variant="ghost" className="text-muted-foreground" disabled={saving}
                  title="Volta ao preço padrão da tabela (ou sem preço)" onClick={() => save(null)}>Limpar</Button>
              )}
              <Button size="sm" variant="outline"
                onClick={() => { setValue(item.sale_price !== null ? String(item.sale_price) : ""); setEditing(true); }}>
                {item.sale_price === null ? "Adicionar preço" : "Editar preço"}
              </Button>
            </div>
          )}
        </div>
      )}
      {item.billing_unit === "metro" && (
        <p className="text-xs text-muted-foreground">Torre cobrada por metro: o preço por peça definido aqui substitui o cálculo pelo metro da linha.</p>
      )}
    </Section>
  );
}

function QuantitySection({ item, canEdit, onSaved }: { item: InventoryItemDetail; canEdit: boolean; onSaved: () => void }) {
  const [mode, setMode] = useState<"entrada" | "baixa" | "contagem">("entrada");
  const [value, setValue] = useState("");
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);

  const submit = async () => {
    const n = Math.trunc(Number(value));
    if (value === "" || Number.isNaN(n) || n < 0 || (mode !== "contagem" && n === 0)) return toast.error("Informe a quantidade.");
    if (mode !== "contagem" && !reason.trim()) return toast.error("Informe o motivo.");
    setSaving(true);
    try {
      if (mode === "contagem") {
        await api.patch(`/inventory/items/${item.id}/`, { qty_total: n });
        toast.success(`Contagem atualizada para ${n}.`);
      } else {
        await api.post(`/inventory/items/${item.id}/adjust/`, { delta: mode === "entrada" ? n : -n, reason });
        toast.success(mode === "entrada" ? `Entrada de ${n} registrada.` : `Baixa de ${n} registrada.`);
      }
      setValue("");
      setReason("");
      onSaved();
    } catch (e) {
      toast.error(errorDetail(e, "Não foi possível salvar."));
    } finally {
      setSaving(false);
    }
  };

  const MODES = [
    { key: "entrada", label: "Entrada", icon: Plus },
    { key: "baixa", label: "Baixa", icon: Minus },
    { key: "contagem", label: "Recontagem", icon: ClipboardCheck },
  ] as const;

  return (
    <Section title="Quantidade">
      <div className="flex items-baseline gap-2">
        <span className="text-3xl font-bold tabular-nums">{item.owned ? item.qty_total ?? "?" : "-"}</span>
        <span className="text-sm text-muted-foreground">
          {!item.owned ? "terceirizado, sem estoque próprio" : item.qty_total === null ? "ainda não contado" : "peças no total"}
          {item.owned && item.approximate_count && item.qty_total !== null && " · contagem aproximada"}
        </span>
      </div>
      {canEdit && item.owned && (
        <div className="rounded-lg border p-3 space-y-3">
          <div className="grid grid-cols-3 gap-1 rounded-md bg-muted p-1">
            {MODES.map(({ key, label, icon: Icon }) => (
              <button key={key} type="button" onClick={() => setMode(key)}
                className={cn("flex items-center justify-center gap-1 rounded px-2 py-1.5 text-xs font-medium transition-colors",
                  mode === key ? "bg-background shadow-sm text-foreground" : "text-muted-foreground hover:text-foreground")}>
                <Icon className="w-3.5 h-3.5 shrink-0" /> <span className="truncate">{label}</span>
              </button>
            ))}
          </div>
          <div className="flex gap-2">
            <Input type="number" min={0} value={value} className={mode === "contagem" ? "flex-1" : "w-24"}
              placeholder={mode === "contagem" ? "Quantidade contada agora" : "Qtd."}
              onChange={(e) => setValue(e.target.value)} onKeyDown={(e) => e.key === "Enter" && submit()} />
            {mode !== "contagem" && (
              <Input value={reason} placeholder={mode === "entrada" ? "Motivo (compra, devolução...)" : "Motivo (quebra, venda, perda...)"}
                onChange={(e) => setReason(e.target.value)} onKeyDown={(e) => e.key === "Enter" && submit()} />
            )}
            <Button size="sm" className="h-10 shrink-0" disabled={saving} onClick={submit}
              variant={mode === "baixa" ? "destructive" : "default"}>
              {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : "Salvar"}
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">
            {mode === "contagem" ? "Use depois de contar as peças: substitui o total e marca a contagem como exata."
              : "Fica registrado nos ajustes de quantidade, com quem fez e quando."}
          </p>
        </div>
      )}
    </Section>
  );
}

/** Histórico dos ajustes de quantidade (Entrada / Baixa / Recontagem). As notas livres saíram da tela,
 * mas continuam gravadas. */
function AdjustmentsSection({ item }: { item: InventoryItemDetail }) {
  const adjustments = item.observations.filter((o) => o.kind === "ajuste");
  if (adjustments.length === 0) return null;
  return (
    <Section title={`Ajustes de quantidade (${adjustments.length})`}>
      <ul className="space-y-2">
        {adjustments.map((o) => (
          <li key={o.id} className="rounded-lg border p-3 text-sm bg-muted/40">
            <p className="whitespace-pre-wrap">{o.text}</p>
            <div className="mt-1 text-xs text-muted-foreground">{o.author_name || "sistema"} · {formatDateTime(o.created_at)}</div>
          </li>
        ))}
      </ul>
    </Section>
  );
}

function ReservationRow({ r, canCancel, onCancel }: { r: InventoryReservation; canCancel: boolean; onCancel: () => void }) {
  return (
    <li className="rounded-lg border p-3 text-sm flex items-start justify-between gap-2">
      <div className="space-y-0.5">
        <div className="font-medium">
          {r.qty} · {r.customer_name || "sem cliente"}
          {r.kit_name && <span className="font-normal text-muted-foreground"> · no kit {r.kit_name}</span>}
        </div>
        <div className="text-xs text-muted-foreground">
          {formatDay(r.start)} a {lastDay(r.end)} · {r.manual ? `manual${r.created_by_name ? ` (${r.created_by_name})` : ""}` : "proposta aceita"}
          {r.status === "retirado" && " · retirado"}
        </div>
        {r.note && <div className="text-xs">{r.note}</div>}
      </div>
      {canCancel && r.manual && r.status === "reservado" && (
        <Button size="sm" variant="ghost" className="text-rose-600" onClick={onCancel}>Cancelar</Button>
      )}
    </li>
  );
}

function ReservationsSection({ item, canEdit, myId, onSaved }: {
  item: InventoryItemDetail; canEdit: boolean; myId?: number; onSaved: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ qty: "", start: today(), end: today(), client_name: "", note: "" });
  const [saving, setSaving] = useState(false);

  const create = async () => {
    setSaving(true);
    try {
      await api.post("/inventory/reservations/", { item_id: item.id, ...form, qty: Number(form.qty) });
      toast.success("Reserva criada.");
      setForm({ qty: "", start: today(), end: today(), client_name: "", note: "" });
      setOpen(false);
      onSaved();
    } catch (e) {
      toast.error(errorDetail(e, "Não foi possível reservar."));
    } finally {
      setSaving(false);
    }
  };
  const cancel = async (id: string) => {
    try {
      await api.delete(`/inventory/reservations/${id}/`);
      toast.success("Reserva cancelada.");
      onSaved();
    } catch (e) {
      toast.error(errorDetail(e, "Não foi possível cancelar."));
    }
  };

  if (!item.reservations_enabled) {
    return (
      <Section title="Reservas">
        <p className="text-sm text-muted-foreground">A reserva de estoque está desligada. O disponível é o total do item.</p>
      </Section>
    );
  }

  return (
    <Section title={`Reservas ativas (${item.reservations.length})`}
      action={item.active && !open && <Button size="sm" variant="outline" onClick={() => setOpen(true)}><CalendarClock className="w-4 h-4" /> Reservar</Button>}>
      {open && (
        <div className="rounded-lg border p-3 space-y-2">
          <div className="grid grid-cols-3 gap-2">
            <div className="space-y-1">
              <Label className="text-xs">Qtd.</Label>
              <Input type="number" min={1} value={form.qty} onChange={(e) => setForm({ ...form, qty: e.target.value })} />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">De</Label>
              <Input type="date" value={form.start} onChange={(e) => setForm({ ...form, start: e.target.value, end: e.target.value > form.end ? e.target.value : form.end })} />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Até</Label>
              <Input type="date" value={form.end} min={form.start} onChange={(e) => setForm({ ...form, end: e.target.value })} />
            </div>
          </div>
          <Input value={form.client_name} placeholder="Para quem (cliente / evento)" onChange={(e) => setForm({ ...form, client_name: e.target.value })} />
          <Input value={form.note} placeholder="Observação (opcional)" onChange={(e) => setForm({ ...form, note: e.target.value })} />
          <div className="flex justify-end gap-2">
            <Button size="sm" variant="ghost" onClick={() => setOpen(false)}>Fechar</Button>
            <Button size="sm" onClick={create} disabled={saving}>{saving && <Loader2 className="w-4 h-4 animate-spin" />}Reservar</Button>
          </div>
        </div>
      )}
      {item.reservations.length === 0 ? (
        <p className="text-sm text-muted-foreground">Nenhuma reserva em andamento.</p>
      ) : (
        <ul className="space-y-2">
          {item.reservations.map((r) => (
            <ReservationRow key={r.id} r={r} canCancel={canEdit || String(myId) === r.created_by} onCancel={() => cancel(r.id)} />
          ))}
        </ul>
      )}
    </Section>
  );
}

export function InventoryItemDialog({ itemId, onClose, canEdit, canEditPrice = false, myId }: {
  itemId: string | null; onClose: () => void; canEdit: boolean; canEditPrice?: boolean; myId?: number;
}) {
  const queryClient = useQueryClient();
  const { data: item, isLoading } = useInventoryItem(itemId);
  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["inventory-item", itemId] });
    queryClient.invalidateQueries({ queryKey: ["inventory"] });
    queryClient.invalidateQueries({ queryKey: ["sales-catalog"] });
  };

  const setActive = async (active: boolean) => {
    if (!item) return;
    if (!active && !window.confirm(`Remover "${item.name}" do estoque? O histórico fica guardado e dá para restaurar.`)) return;
    try {
      if (active) await api.patch(`/inventory/items/${item.id}/`, { active: true });
      else await api.delete(`/inventory/items/${item.id}/`);
      toast.success(active ? "Item restaurado." : "Item removido do estoque.");
      refresh();
    } catch (e) {
      toast.error(errorDetail(e, "Não foi possível alterar o item."));
    }
  };
  const deleteForever = async () => {
    if (!item || !window.confirm(`Apagar "${item.name}" de vez? Não dá para desfazer.`)) return;
    try {
      await api.delete(`/inventory/items/${item.id}/`, { params: { permanent: 1 } });
      toast.success("Item apagado.");
      queryClient.invalidateQueries({ queryKey: ["inventory"] });
      onClose();
    } catch (e) {
      toast.error(errorDetail(e, "Não foi possível apagar."));
    }
  };

  return (
    <Dialog open={!!itemId} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-xl sm:max-h-[90vh]" onOpenAutoFocus={(e) => { e.preventDefault(); (e.currentTarget as HTMLElement).focus(); }}>
        {isLoading || !item ? (
          <div className="flex justify-center py-10">
            <DialogTitle className="sr-only">Carregando item</DialogTitle>
            <Loader2 className="w-6 h-6 animate-spin" />
          </div>
        ) : (
          <div className="space-y-6">
            <DialogHeader className="text-left space-y-1">
              <DialogTitle className="pr-6">{item.name}</DialogTitle>
              <DialogDescription className="sr-only">Preço, quantidade, reservas e movimentações do item.</DialogDescription>
              <div className="flex flex-wrap gap-1 text-xs text-muted-foreground items-center">
                <code>{item.code}</code>
                {!item.active && <Badge variant="destructive" className="text-[10px]">removido</Badge>}
                {!item.owned && <Badge variant="outline" className="text-[10px]">terceirizado</Badge>}
              </div>
            </DialogHeader>

            <PriceSection item={item} canEdit={canEditPrice} onSaved={refresh} />
            <QuantitySection item={item} canEdit={canEdit} onSaved={refresh} />
            <DetailsSection item={item} canEdit={canEdit} onSaved={refresh} />
            {item.kits?.length > 0 && (
              <Section title={`Peça de ${item.kits.length} kit${item.kits.length === 1 ? "" : "s"}`}>
                <ul className="flex flex-wrap gap-1.5">
                  {item.kits.map((k) => (
                    <li key={k.id} className="inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs">
                      <Boxes className="w-3.5 h-3.5 text-primary" />{k.name}
                      <span className="text-muted-foreground">· {k.qty} por kit</span>
                    </li>
                  ))}
                </ul>
                <p className="text-xs text-muted-foreground">Para remover este item do estoque, tire-o desses kits antes.</p>
              </Section>
            )}
            <ReservationsSection item={item} canEdit={canEdit} myId={myId} onSaved={refresh} />
            <AdjustmentsSection item={item} />

            {item.movements.length > 0 && (
              <Section title="Últimas movimentações">
                <ul className="text-sm divide-y">
                  {item.movements.map((m) => (
                    <li key={m.id} className="py-1.5 flex justify-between gap-2">
                      <span>{m.type === "saida" ? "Saída" : "Retorno"} de {m.qty}{m.customer_name ? ` · ${m.customer_name}` : ""}</span>
                      <span className="text-xs text-muted-foreground">{formatDateTime(m.date)}</span>
                    </li>
                  ))}
                </ul>
              </Section>
            )}

            {canEdit && (
              <div className="border-t pt-4 flex flex-wrap gap-2 justify-end">
                {item.active ? (
                  <Button size="sm" variant="outline" className="text-rose-600 hover:bg-rose-50 hover:text-rose-700 dark:hover:bg-rose-950" onClick={() => setActive(false)}>
                    <Trash2 className="w-4 h-4" /> Remover do estoque
                  </Button>
                ) : (
                  <>
                    <Button size="sm" variant="ghost" className="text-rose-600" onClick={deleteForever}>Apagar de vez</Button>
                    <Button size="sm" onClick={() => setActive(true)}><ArchiveRestore className="w-4 h-4" /> Restaurar</Button>
                  </>
                )}
              </div>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
