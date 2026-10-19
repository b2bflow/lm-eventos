import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import api from "@/services/api";
import { BILLING_UNITS, INVENTORY_LINES } from "./constants";

const empty = (line?: string) => ({
  name: "", line: line || "Acessórios", size: "", billing_unit: "unidade", qty: "", owned: true, description: "",
});

export function NewInventoryItemDialog({ open, onOpenChange, defaultLine, onCreated }: {
  open: boolean; onOpenChange: (open: boolean) => void; defaultLine?: string; onCreated: (id: string) => void;
}) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState(empty(defaultLine));
  const [saving, setSaving] = useState(false);

  const close = (next: boolean) => {
    if (!next) setForm(empty(defaultLine));
    onOpenChange(next);
  };

  const create = async () => {
    if (!form.name.trim()) return toast.error("Informe o nome do equipamento.");
    setSaving(true);
    try {
      const { data } = await api.post<{ id: string }>("/inventory/items/", {
        name: form.name, line: form.line, size: form.size || null, billing_unit: form.billing_unit,
        owned: form.owned, description: form.description || null,
        qty_total: form.owned && form.qty !== "" ? Math.trunc(Number(form.qty)) : null,
      });
      toast.success(`${form.name} adicionado ao estoque.`);
      queryClient.invalidateQueries({ queryKey: ["inventory"] });
      close(false);
      onCreated(data.id);
    } catch (e) {
      toast.error((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail || "Não foi possível criar o item.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader><DialogTitle>Novo item no estoque</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1">
            <Label className="text-xs">Nome</Label>
            <Input autoFocus value={form.name} placeholder="ex.: Moving head beam 230W" onChange={(e) => setForm({ ...form, name: e.target.value })} />
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
            <div className="space-y-1">
              <Label className="text-xs">Tamanho</Label>
              <Input value={form.size} placeholder="opcional" onChange={(e) => setForm({ ...form, size: e.target.value })} />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Quantidade</Label>
              <Input type="number" min={0} value={form.qty} disabled={!form.owned} placeholder="não contado"
                onChange={(e) => setForm({ ...form, qty: e.target.value })} />
            </div>
          </div>
          <label className="flex items-center gap-2 text-sm">
            <Switch checked={!form.owned} onCheckedChange={(v) => setForm({ ...form, owned: !v })} />
            Terceirizado (não tem quantidade própria)
          </label>
          <div className="space-y-1">
            <Label className="text-xs">Descrição</Label>
            <Textarea rows={3} value={form.description} placeholder="Modelo, especificação, acessórios..."
              onChange={(e) => setForm({ ...form, description: e.target.value })} />
          </div>
          <p className="text-xs text-muted-foreground">O preço de venda vem da tabela de preços. Item novo aparece como "sem preço" até ser incluído lá.</p>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => close(false)}>Cancelar</Button>
          <Button onClick={create} disabled={saving}>{saving && <Loader2 className="w-4 h-4 animate-spin" />}Adicionar</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
