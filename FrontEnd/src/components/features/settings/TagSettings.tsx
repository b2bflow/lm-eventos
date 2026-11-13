import { useState } from "react";
import { Check, Loader2, Pencil, Plus, Trash2, X } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { cn } from "@/lib/utils";
import {
  TAG_COLOR_DOTS, TAG_COLOR_LABELS, TAG_COLORS, useCreateTag, useDeleteTag, useTags, useUpdateTag, type CustomerTag,
} from "@/hooks/useTags";
import { TagChip } from "@/components/domain/tags/TagChips";

function ColorSelect({ value, onChange, disabled }: { value: string; onChange: (color: string) => void; disabled?: boolean }) {
  return (
    <Select value={value} onValueChange={onChange} disabled={disabled}>
      <SelectTrigger className="w-[150px] h-9" aria-label="Cor"><SelectValue /></SelectTrigger>
      <SelectContent>
        {TAG_COLORS.map((color) => (
          <SelectItem key={color} value={color}>
            <span className="flex items-center gap-2">
              <span className={cn("w-3 h-3 rounded-full", TAG_COLOR_DOTS[color])} /> {TAG_COLOR_LABELS[color]}
            </span>
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

function TagRow({ tag, onDelete }: { tag: CustomerTag; onDelete: () => void }) {
  const update = useUpdateTag();
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(tag.name);

  const saveName = () => {
    const next = name.trim();
    if (!next || next === tag.name) {
      setEditing(false);
      setName(tag.name);
      return;
    }
    update.mutate({ id: tag.id, name: next }, {
      onSuccess: () => { setEditing(false); toast.success("Tag renomeada."); },
    });
  };

  return (
    <li className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-3 py-3">
      <div className="flex-1 min-w-0 flex items-center gap-2">
        {editing ? (
          <>
            <Input value={name} onChange={(e) => setName(e.target.value)} maxLength={40} autoFocus className="h-9"
              aria-label="Nome da tag"
              onKeyDown={(e) => {
                if (e.key === "Enter") saveName();
                if (e.key === "Escape") { setEditing(false); setName(tag.name); }
              }} />
            <Button size="icon" variant="ghost" className="h-9 w-9 shrink-0" onClick={saveName} disabled={update.isPending} title="Salvar nome">
              {update.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />}
            </Button>
            <Button size="icon" variant="ghost" className="h-9 w-9 shrink-0" onClick={() => { setEditing(false); setName(tag.name); }} title="Cancelar">
              <X className="w-4 h-4" />
            </Button>
          </>
        ) : (
          <>
            <TagChip tagKey={tag.key} tag={tag} className="text-xs" />
            {tag.builtin && <span className="text-[11px] text-muted-foreground">automática</span>}
            <Button size="icon" variant="ghost" className="h-8 w-8 shrink-0 text-muted-foreground" onClick={() => setEditing(true)} title="Renomear">
              <Pencil className="w-3.5 h-3.5" />
            </Button>
          </>
        )}
      </div>
      <div className="flex items-center gap-2">
        <span className="text-xs text-muted-foreground w-24 sm:text-right tabular-nums">
          {tag.count ?? 0} contato{tag.count === 1 ? "" : "s"}
        </span>
        <ColorSelect value={tag.color} disabled={update.isPending}
          onChange={(color) => update.mutate({ id: tag.id, color })} />
        <Button size="icon" variant="ghost" className="h-9 w-9 text-muted-foreground hover:text-rose-600 hover:bg-rose-500/10"
          onClick={onDelete} disabled={tag.builtin}
          title={tag.builtin ? "A IA coloca esta tag sozinha: não pode ser excluída" : "Excluir tag"}>
          <Trash2 className="w-4 h-4" />
        </Button>
      </div>
    </li>
  );
}

/** Configurações > Tags (admin): criar, renomear, trocar a cor e excluir as tags dos clientes. */
export function TagSettings() {
  const { data: tags = [], isLoading, isError } = useTags(true);
  const create = useCreateTag();
  const remove = useDeleteTag();
  const [newName, setNewName] = useState("");
  const [newColor, setNewColor] = useState<string>("emerald");
  const [deleting, setDeleting] = useState<CustomerTag | null>(null);
  const sorted = [...tags].sort((a, b) => a.name.localeCompare(b.name, "pt-BR"));

  const add = () => {
    const name = newName.trim();
    if (!name) return;
    create.mutate({ name, color: newColor }, {
      onSuccess: (tag) => {
        setNewName("");
        toast.success(tags.some((t) => t.key === tag.key) ? `A tag ${tag.name} já existia.` : "Tag criada.");
      },
    });
  };

  if (isError) return <p className="p-8 text-center text-sm text-destructive">Não foi possível carregar as tags.</p>;

  return (
    <div className="space-y-6">
      <section className="p-6 rounded-2xl border border-border/50 bg-background/40 shadow-sm">
        <div className="mb-4">
          <h3 className="text-lg font-semibold text-foreground">Tags dos clientes</h3>
          <p className="text-sm text-muted-foreground">
            A equipe põe e tira as tags no contato e no perfil do cliente da conversa, e pode criar tags novas por lá.
            Aqui você renomeia, troca a cor e exclui. As automáticas (colocadas pela IA) não podem ser excluídas.
          </p>
        </div>
        <div className="flex flex-col sm:flex-row gap-2">
          <Input value={newName} onChange={(e) => setNewName(e.target.value)} maxLength={40} placeholder="Nome da tag nova"
            aria-label="Nome da tag nova" className="sm:flex-1" onKeyDown={(e) => e.key === "Enter" && add()} />
          <div className="flex gap-2">
            <ColorSelect value={newColor} onChange={setNewColor} />
            <Button onClick={add} disabled={!newName.trim() || create.isPending}>
              {create.isPending ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : <Plus className="w-4 h-4 mr-1" />} Criar tag
            </Button>
          </div>
        </div>

        {isLoading ? (
          <div className="flex justify-center p-8"><Loader2 className="animate-spin text-primary w-6 h-6" /></div>
        ) : (
          <ul className="mt-4 divide-y divide-border/50">
            {sorted.map((tag) => <TagRow key={tag.id} tag={tag} onDelete={() => setDeleting(tag)} />)}
          </ul>
        )}
      </section>

      <Dialog open={!!deleting} onOpenChange={(open) => !open && setDeleting(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Excluir tag</DialogTitle>
            <DialogDescription>
              A tag {deleting?.name} sai do catálogo e de {deleting?.count ?? 0} contato{deleting?.count === 1 ? "" : "s"}.
              Não dá para desfazer.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleting(null)}>Cancelar</Button>
            <Button variant="destructive" disabled={remove.isPending}
              onClick={() => deleting && remove.mutate(deleting.id, {
                onSuccess: () => { toast.success("Tag excluída."); setDeleting(null); },
              })}>
              <Trash2 className="w-4 h-4 mr-1.5" /> Excluir tag
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
