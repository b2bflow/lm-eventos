import { useEffect, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  AlertTriangle, ArchiveRestore, Boxes, CalendarClock, Copy, Loader2, Minus, Plus, Search, Trash2, X,
} from "lucide-react";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import api from "@/services/api";
import { cn } from "@/lib/utils";
import { formatBRL, formatDay } from "@/lib/format";
import { useInventory, useKit, type InventoryKitDetail, type InventoryRow } from "@/hooks/useSales";
import { INVENTORY_LINES } from "./constants";

const normalize = (text: string) => text.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

function errorDetail(error: unknown, fallback: string) {
  return (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail || fallback;
}

/** Fim da reserva é gravado exclusivo (dia seguinte): mostra o último dia de uso. */
function lastDay(end: string) {
  const d = new Date(`${end.slice(0, 10)}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() - 1);
  return formatDay(d.toISOString());
}

type Piece = { code: string; qty: number };
type KitForm = { name: string; line: string; description: string; show_pieces: boolean; price: string; pieces: Piece[] };

const emptyForm = (): KitForm => ({ name: "", line: "Som", description: "", show_pieces: true, price: "", pieces: [] });

const toForm = (kit: InventoryKitDetail): KitForm => ({
  name: kit.name, line: kit.line, description: kit.description || "", show_pieces: kit.show_pieces,
  price: kit.sale_price === null ? "" : String(kit.sale_price).replace(".", ","),
  pieces: kit.pieces.map((p) => ({ code: p.code, qty: p.qty })),
});

/** Quantos kits dá para montar com o disponível do período (pela peça que acaba primeiro). */
function buildable(pieces: Piece[], rows: Map<string, InventoryRow>) {
  let fits: number | null = null;
  let limiting: string | null = null;
  for (const piece of pieces) {
    const row = rows.get(piece.code);
    if (!row || row.available === null || !piece.qty) continue;
    const n = Math.max(0, Math.floor(row.available / piece.qty));
    if (fits === null || n < fits) { fits = n; limiting = row.name; }
  }
  return { fits, limiting };
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

function PiecePicker({ rows, exclude, onPick }: { rows: InventoryRow[]; exclude: Set<string>; onPick: (code: string) => void }) {
  const [query, setQuery] = useState("");
  const terms = normalize(query).split(/\s+/).filter(Boolean);
  const matches = terms.length
    ? rows.filter((r) => r.active && !exclude.has(r.code)
      && terms.every((t) => normalize(`${r.name} ${r.code} ${r.line}`).includes(t))).slice(0, 8)
    : [];
  return (
    <div className="relative">
      <Search className="absolute left-2.5 top-2.5 w-4 h-4 text-muted-foreground" />
      <Input value={query} placeholder="Adicionar peça: busque no estoque (ex.: caixa, microfone, pedestal)"
        className="pl-8" onChange={(e) => setQuery(e.target.value)} />
      {matches.length > 0 && (
        <ul className="absolute z-20 mt-1 w-full rounded-lg border bg-popover shadow-lg max-h-64 overflow-auto">
          {matches.map((r) => (
            <li key={r.code}>
              <button type="button" className="w-full flex items-center justify-between gap-2 px-3 py-2 text-left text-sm hover:bg-muted"
                onClick={() => { onPick(r.code); setQuery(""); }}>
                <span className="min-w-0 truncate">{r.name} <span className="text-xs text-muted-foreground">· {r.line}</span></span>
                <span className="text-xs text-muted-foreground shrink-0">
                  {r.available === null ? (r.owned ? "sem contagem" : "terceirizado") : `${r.available} disp.`}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {terms.length > 0 && matches.length === 0 && (
        <p className="text-xs text-muted-foreground mt-1">Nada no estoque com "{query}". Cadastre a peça em "Novo item" antes.</p>
      )}
    </div>
  );
}

function KitReservations({ kit, start, end, canCancel, onSaved }: {
  kit: InventoryKitDetail; start: string; end: string; canCancel: (createdBy: string | null) => boolean; onSaved: () => void;
}) {
  const blank = { qty: "1", start, end, client_name: "", note: "" };
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(blank);
  const [saving, setSaving] = useState(false);

  const create = async () => {
    setSaving(true);
    try {
      await api.post(`/inventory/kits/${kit.id}/reserve/`, { ...form, qty: Number(form.qty) });
      toast.success("Kit reservado: todas as peças ficaram reservadas no período.");
      setForm(blank);
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
      toast.success("Reserva do kit cancelada (todas as peças).");
      onSaved();
    } catch (e) {
      toast.error(errorDetail(e, "Não foi possível cancelar."));
    }
  };

  return (
    <Section title={`Reservas do kit (${kit.reservations.length})`}
      action={kit.active && kit.pieces.length > 0 && !open && (
        <Button size="sm" variant="outline" onClick={() => setOpen(true)}><CalendarClock className="w-4 h-4" /> Reservar kit</Button>
      )}>
      {open && (
        <div className="rounded-lg border p-3 space-y-2">
          <div className="grid grid-cols-3 gap-2">
            <div className="space-y-1">
              <Label className="text-xs">Kits</Label>
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
          <p className="text-xs text-muted-foreground">Reserva cada peça do kit. Se faltar alguma no período, nada é reservado.</p>
          <div className="flex justify-end gap-2">
            <Button size="sm" variant="ghost" onClick={() => setOpen(false)}>Fechar</Button>
            <Button size="sm" onClick={create} disabled={saving}>{saving && <Loader2 className="w-4 h-4 animate-spin" />}Reservar</Button>
          </div>
        </div>
      )}
      {kit.reservations.length === 0 ? (
        <p className="text-sm text-muted-foreground">Nenhuma reserva manual deste kit em andamento.</p>
      ) : (
        <ul className="space-y-2">
          {kit.reservations.map((r) => (
            <li key={r.id} className="rounded-lg border p-3 text-sm flex items-start justify-between gap-2">
              <div className="space-y-0.5">
                <div className="font-medium">{r.kits ?? "?"} kit(s) · {r.customer_name || "sem cliente"}</div>
                <div className="text-xs text-muted-foreground">
                  {formatDay(r.start)} a {lastDay(r.end)}{r.created_by_name ? ` · ${r.created_by_name}` : ""}
                  {r.status === "retirado" && " · retirado"}
                </div>
                {r.note && <div className="text-xs">{r.note}</div>}
              </div>
              {canCancel(r.created_by) && r.status === "reservado" && (
                <Button size="sm" variant="ghost" className="text-rose-600" onClick={() => cancel(r.id)}>Cancelar</Button>
              )}
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}

/**
 * Kit do estoque: criar (kitId null e `creating`) ou ver/editar. O preço é do kit; o estoque, a reserva
 * e o PDF trabalham com as peças.
 */
export function KitDialog({ kitId, creating, onClose, onCreated, start, end, canEdit, canEditPrice, reservationsOn, myId }: {
  kitId: string | null; creating: boolean; onClose: () => void; onCreated: (id: string) => void;
  start: string; end: string; canEdit: boolean; canEditPrice: boolean; reservationsOn: boolean; myId?: number;
}) {
  const queryClient = useQueryClient();
  const { data: kit, isLoading } = useKit(creating ? null : kitId, start, end);
  const { data: rows = [] } = useInventory(undefined, start, end);
  const [form, setForm] = useState<KitForm>(emptyForm());
  const [copyOf, setCopyOf] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const open = creating || !!kitId;
  const isNew = creating || !!copyOf;

  useEffect(() => {
    if (!open) { setForm(emptyForm()); setCopyOf(null); }
  }, [open]);
  useEffect(() => { if (kit && !copyOf) setForm(toForm(kit)); }, [kit, copyOf]);

  const rowsByCode = useMemo(() => new Map(rows.map((r) => [r.code, r])), [rows]);
  const preview = buildable(form.pieces, rowsByCode);
  const builtin = !isNew && !!kit?.builtin;
  const editable = canEdit && (isNew || !!kit?.active);
  const dirty = isNew || (!!kit && JSON.stringify(form) !== JSON.stringify(toForm(kit)));

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["inventory-kits"] });
    queryClient.invalidateQueries({ queryKey: ["inventory-kit"] });
    queryClient.invalidateQueries({ queryKey: ["inventory"] });
    queryClient.invalidateQueries({ queryKey: ["inventory-item"] });
    queryClient.invalidateQueries({ queryKey: ["sales-catalog"] });
    queryClient.invalidateQueries({ queryKey: ["sales-prices"] });
  };

  const setPiece = (code: string, qty: number) =>
    setForm({ ...form, pieces: form.pieces.map((p) => (p.code === code ? { ...p, qty: Math.max(0, qty) } : p)) });

  const save = async () => {
    if (!form.name.trim()) return toast.error("Informe o nome do kit.");
    if (!form.pieces.length && !builtin) return toast.error("Adicione ao menos uma peça.");
    if (form.pieces.some((p) => !(p.qty > 0))) return toast.error("Toda peça precisa de quantidade maior que zero.");
    const body: Record<string, unknown> = {
      pieces: form.pieces, description: form.description, show_pieces: form.show_pieces,
      ...(builtin ? {} : { name: form.name.trim(), line: form.line }),
    };
    const priceChanged = isNew ? form.price.trim() !== "" : form.price !== toForm(kit!).price;
    if (canEditPrice && priceChanged) body.sale_price = form.price.trim() || null;
    setSaving(true);
    try {
      const params = { start, end };
      if (isNew) {
        const { data } = await api.post<InventoryKitDetail>("/inventory/kits/", body, { params });
        toast.success(`Kit ${data.name} criado.`);
        setCopyOf(null);
        refresh();
        onCreated(data.id);
      } else {
        await api.patch(`/inventory/kits/${kit!.id}/`, body, { params });
        toast.success("Kit salvo.");
        refresh();
      }
    } catch (e) {
      toast.error(errorDetail(e, "Não foi possível salvar o kit."));
    } finally {
      setSaving(false);
    }
  };

  const setActive = async (active: boolean) => {
    if (!kit) return;
    if (!active && !window.confirm(`Remover o kit "${kit.name}"? Sai da calculadora; propostas já feitas continuam valendo e dá para restaurar.`)) return;
    try {
      if (active) await api.patch(`/inventory/kits/${kit.id}/`, { active: true });
      else await api.delete(`/inventory/kits/${kit.id}/`);
      toast.success(active ? "Kit restaurado." : "Kit removido.");
      refresh();
    } catch (e) {
      toast.error(errorDetail(e, "Não foi possível alterar o kit."));
    }
  };

  const duplicate = () => {
    if (!kit) return;
    setCopyOf(kit.id);
    setForm({ ...toForm(kit), name: `${kit.name} (cópia)`, line: kit.line });
  };

  const loading = !isNew && (isLoading || !kit);
  const title = isNew ? (copyOf ? "Duplicar kit" : "Novo kit") : kit?.name;

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="sm:max-w-2xl max-h-[90vh] overflow-y-auto"
        onOpenAutoFocus={(e) => { if (!isNew) { e.preventDefault(); (e.currentTarget as HTMLElement).focus(); } }}>
        {loading ? (
          <div className="flex justify-center py-10">
            <DialogTitle className="sr-only">Carregando kit</DialogTitle>
            <Loader2 className="w-6 h-6 animate-spin" />
          </div>
        ) : (
          <div className="space-y-6">
            <DialogHeader className="text-left space-y-1">
              <DialogTitle className="pr-6 flex items-center gap-2"><Boxes className="w-5 h-5 text-primary" />{title}</DialogTitle>
              <DialogDescription>
                O cliente paga o preço do kit; o estoque confere e reserva cada peça
                {form.show_pieces ? " e a proposta em PDF lista as peças." : "."}
              </DialogDescription>
              {!isNew && kit && (
                <div className="flex flex-wrap gap-1 text-xs text-muted-foreground items-center">
                  <code>{kit.code}</code>
                  {kit.builtin && <Badge variant="outline" className="text-[10px]">faixa de som da calculadora</Badge>}
                  {!kit.active && <Badge variant="destructive" className="text-[10px]">removido</Badge>}
                </div>
              )}
            </DialogHeader>

            {/* Resumo: quantos dá para montar no período */}
            <div className={cn("rounded-xl border p-3 flex items-center justify-between gap-3",
              preview.fits === 0 ? "border-rose-500/40 bg-rose-500/5" : "bg-muted/30")}>
              <div className="text-sm">
                <div className="font-medium">
                  {preview.fits === null
                    ? "Sem peças contadas para calcular"
                    : `Dá para montar ${preview.fits} kit${preview.fits === 1 ? "" : "s"}`}
                </div>
                <div className="text-xs text-muted-foreground">
                  {reservationsOn ? `De ${formatDay(start)} a ${formatDay(end)}, descontando as reservas` : "Pelo total do estoque"}
                  {preview.limiting && preview.fits !== null && ` · limitado por ${preview.limiting}`}
                </div>
              </div>
              <div className="text-right shrink-0">
                <div className="text-xs text-muted-foreground">Preço do kit</div>
                <div className="font-semibold tabular-nums whitespace-nowrap">{kit?.sale_price != null && !isNew ? formatBRL(kit.sale_price) : form.price ? `R$ ${form.price}` : "sem preço"}</div>
              </div>
            </div>
            {!isNew && kit && kit.problems.length > 0 && (
              <ul className="text-xs text-amber-700 dark:text-amber-300 space-y-1">
                {kit.problems.map((p) => <li key={p} className="flex gap-1.5"><AlertTriangle className="w-3.5 h-3.5 shrink-0" />{p}</li>)}
              </ul>
            )}

            <Section title="Dados do kit">
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div className="space-y-1 sm:col-span-2">
                  <Label className="text-xs">Nome</Label>
                  <Input autoFocus={isNew} value={form.name} disabled={!editable || builtin}
                    placeholder="ex.: Som para até 150 pessoas" onChange={(e) => setForm({ ...form, name: e.target.value })} />
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">Linha</Label>
                  <Select value={form.line} disabled={!editable || builtin} onValueChange={(line) => setForm({ ...form, line })}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>{INVENTORY_LINES.map((l) => <SelectItem key={l} value={l}>{l}</SelectItem>)}</SelectContent>
                  </Select>
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">Preço de venda (R$ por kit)</Label>
                  <Input inputMode="decimal" value={form.price} disabled={!canEditPrice || !editable} placeholder="sem preço"
                    onChange={(e) => setForm({ ...form, price: e.target.value })} />
                </div>
                <div className="space-y-1 sm:col-span-2">
                  <Label className="text-xs">Na proposta (PDF)</Label>
                  <div className="grid grid-cols-2 gap-2" role="radiogroup" aria-label="Como o kit sai no PDF">
                    {([[true, "Lista as peças", "04 Caixa de som ativa…"], [false, "Mostra o nome do kit", form.name || "Nome do kit"]] as const).map(([value, label, hint]) => (
                      <button key={label} type="button" role="radio" aria-checked={form.show_pieces === value} disabled={!editable}
                        onClick={() => setForm({ ...form, show_pieces: value })}
                        className={cn("text-left rounded-lg border px-3 py-1.5 text-sm transition-colors disabled:opacity-60",
                          form.show_pieces === value ? "border-primary bg-primary/5" : "hover:bg-secondary")}>
                        <span className="font-medium">{label}</span>
                        <span className="block text-xs text-muted-foreground truncate">{hint}</span>
                      </button>
                    ))}
                  </div>
                </div>
              </div>
              {!canEditPrice && editable && <p className="text-xs text-muted-foreground">Só a Erica (admin) define o preço do kit.</p>}
              {builtin && (
                <p className="text-xs text-muted-foreground">
                  A calculadora escolhe este kit pelo público. Nome e linha são fixos; o preço também fica em Configurações &gt; Valores.
                </p>
              )}
              <div className="space-y-1">
                <Label className="text-xs">Descrição interna (opcional)</Label>
                <Textarea rows={2} value={form.description} disabled={!editable} placeholder="ex.: para festa até 150 pessoas, cabos inclusos"
                  onChange={(e) => setForm({ ...form, description: e.target.value })} />
              </div>
            </Section>

            <Section title={`Peças (${form.pieces.length})`}>
              {form.pieces.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  {builtin ? "Sem peças: o PDF mostra o nome do kit e o estoque não confere nada." : "Nenhuma peça ainda. Busque abaixo."}
                </p>
              ) : (
                <ul className="rounded-lg border divide-y">
                  {form.pieces.map((piece) => {
                    const row = rowsByCode.get(piece.code);
                    const kitPiece = kit?.pieces.find((p) => p.code === piece.code);
                    const need = piece.qty;
                    const short = row?.available != null && row.available < need;
                    return (
                      <li key={piece.code} className="flex items-center gap-3 px-3 py-2">
                        <div className="flex-1 min-w-0">
                          <div className="text-sm font-medium truncate">{kitPiece?.name || row?.name || piece.code}</div>
                          <div className={cn("text-xs", short ? "text-rose-600 dark:text-rose-400" : "text-muted-foreground")}>
                            {!row ? "removido do estoque" : row.available === null
                              ? (row.owned ? "sem contagem (não limita)" : "terceirizado (não limita)")
                              : `${row.available} disponível de ${row.qty_total ?? 0}`}
                          </div>
                        </div>
                        {editable ? (
                          <div className="flex items-center gap-1 shrink-0">
                            <Button type="button" size="icon" variant="outline" className="h-8 w-8" onClick={() => setPiece(piece.code, piece.qty - 1)}
                              disabled={piece.qty <= 1} aria-label="Menos"><Minus className="w-3.5 h-3.5" /></Button>
                            <Input type="number" min={1} className="w-16 h-8 text-center" value={piece.qty || ""}
                              onChange={(e) => setPiece(piece.code, Number(e.target.value) || 0)} aria-label={`Quantidade de ${row?.name || piece.code}`} />
                            <Button type="button" size="icon" variant="outline" className="h-8 w-8" onClick={() => setPiece(piece.code, piece.qty + 1)}
                              aria-label="Mais"><Plus className="w-3.5 h-3.5" /></Button>
                            <Button type="button" size="icon" variant="ghost" className="h-8 w-8 text-muted-foreground hover:text-rose-600"
                              onClick={() => setForm({ ...form, pieces: form.pieces.filter((p) => p.code !== piece.code) })}
                              aria-label="Tirar do kit"><X className="w-4 h-4" /></Button>
                          </div>
                        ) : (
                          <span className="text-sm tabular-nums shrink-0">{piece.qty} por kit</span>
                        )}
                      </li>
                    );
                  })}
                </ul>
              )}
              {editable && (
                <PiecePicker rows={rows} exclude={new Set(form.pieces.map((p) => p.code))}
                  onPick={(code) => setForm({ ...form, pieces: [...form.pieces, { code, qty: 1 }] })} />
              )}
            </Section>

            {editable && dirty && (
              <DialogFooter className="gap-2">
                <Button variant="ghost" onClick={() => (copyOf ? (setCopyOf(null), kit && setForm(toForm(kit))) : isNew ? onClose() : kit && setForm(toForm(kit)))}>
                  {isNew && !copyOf ? "Cancelar" : "Descartar"}
                </Button>
                <Button onClick={save} disabled={saving}>{saving && <Loader2 className="w-4 h-4 animate-spin" />}{isNew ? "Criar kit" : "Salvar kit"}</Button>
              </DialogFooter>
            )}

            {!isNew && kit && reservationsOn && (
              <KitReservations kit={kit} start={start} end={end} onSaved={refresh}
                canCancel={(createdBy) => canEdit || String(myId) === createdBy} />
            )}

            {!isNew && kit && canEdit && (
              <div className="border-t pt-4 flex flex-wrap gap-2 justify-end">
                {!kit.builtin && <Button size="sm" variant="outline" onClick={duplicate}><Copy className="w-4 h-4" /> Duplicar</Button>}
                {!kit.builtin && (kit.active ? (
                  <Button size="sm" variant="outline" className="text-rose-600 hover:bg-rose-50 hover:text-rose-700 dark:hover:bg-rose-950" onClick={() => setActive(false)}>
                    <Trash2 className="w-4 h-4" /> Remover kit
                  </Button>
                ) : (
                  <Button size="sm" onClick={() => setActive(true)}><ArchiveRestore className="w-4 h-4" /> Restaurar</Button>
                ))}
              </div>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
