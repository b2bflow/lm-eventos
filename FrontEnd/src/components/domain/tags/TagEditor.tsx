import { useEffect, useMemo, useRef, useState } from "react";
import { Loader2, Plus, Tag as TagIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";
import { TAG_COLOR_DOTS, tagKey, useCreateTag, useSetCustomerTags, useTags } from "@/hooks/useTags";
import { TagChip } from "./TagChips";

const normalize = (text: string) => text.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

/**
 * Tags do cliente com edição: tira pelo X e põe pelo "Adicionar tag" (escolhe uma existente ou cria
 * digitando o nome). Grava na hora (PUT /crm/contacts/<id>/tags/).
 */
export function TagEditor({ customerId, value, onChange, disabled }: {
  customerId: string;
  value?: string[] | null;
  onChange?: (tags: string[]) => void;
  disabled?: boolean;
}) {
  const { data: catalog = [], isLoading } = useTags();
  const setTags = useSetCustomerTags();
  const createTag = useCreateTag();
  const [current, setCurrent] = useState<string[]>(value ?? []);
  const [open, setOpen] = useState(false);
  const [term, setTerm] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const valueKey = (value ?? []).join("|");
  useEffect(() => {
    setCurrent(value ?? []);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [customerId, valueKey]);

  const byKey = useMemo(() => new Map(catalog.map((tag) => [tag.key, tag])), [catalog]);
  const busy = setTags.isPending || createTag.isPending;

  const save = (tags: string[]) => {
    const previous = current;
    setCurrent(tags);
    setTags.mutate({ customerId, tags }, {
      onSuccess: (data) => {
        setCurrent(data.tags);
        onChange?.(data.tags);
      },
      onError: () => setCurrent(previous),
    });
  };

  const typedKey = tagKey(term);
  const options = useMemo(() => {
    const words = normalize(term.trim()).split(/\s+/).filter(Boolean);
    return catalog
      .filter((tag) => !current.includes(tag.key))
      .filter((tag) => words.every((word) => normalize(tag.name).includes(word)))
      .sort((a, b) => {
        // Quem começa com o que foi digitado vem primeiro.
        const starts = (name: string) => (words[0] && normalize(name).startsWith(words[0]) ? 0 : 1);
        return starts(a.name) - starts(b.name) || a.name.localeCompare(b.name, "pt-BR");
      });
  }, [catalog, current, term]);
  // Mesmo nome de uma tag existente (renomear não muda a chave): escolhe ela em vez de criar outra.
  const exact = typedKey
    ? byKey.get(typedKey) ?? catalog.find((tag) => tagKey(tag.name) === typedKey)
    : undefined;
  const canCreate = !!typedKey && !exact && term.trim().length <= 40;

  const add = (key: string) => {
    if (current.includes(key)) return;
    save([...current, key]);
    setTerm("");
    setOpen(false);
  };

  const create = () => {
    const name = term.trim();
    if (!name) return;
    createTag.mutate({ name }, { onSuccess: (tag) => add(tag.key) });
  };

  const pickFirst = () => {
    if (exact && !current.includes(exact.key)) add(exact.key);
    else if (options[0]) add(options[0].key);
    else if (canCreate) create();
  };

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {current.length === 0 && !open && (
        <span className="text-xs text-muted-foreground">Nenhuma tag.</span>
      )}
      {current.map((key) => (
        <TagChip key={key} tagKey={key} tag={byKey.get(key)} removing={busy}
          onRemove={disabled ? undefined : () => save(current.filter((k) => k !== key))} />
      ))}
      {!disabled && (
        <Popover open={open} onOpenChange={(next) => { setOpen(next); if (!next) setTerm(""); }}>
          <PopoverTrigger asChild>
            <Button type="button" size="sm" variant="outline" className="h-6 px-2 text-[11px] rounded-full" disabled={busy}>
              {busy ? <Loader2 className="w-3 h-3 mr-1 animate-spin" /> : <Plus className="w-3 h-3 mr-1" />}
              Adicionar tag
            </Button>
          </PopoverTrigger>
          <PopoverContent align="start" className="w-64 p-2" onOpenAutoFocus={(e) => { e.preventDefault(); inputRef.current?.focus(); }}>
            <Input ref={inputRef} value={term} onChange={(e) => setTerm(e.target.value)} maxLength={40}
              placeholder="Buscar ou criar tag" className="h-8 text-sm" aria-label="Buscar ou criar tag"
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  pickFirst();
                }
              }} />
            <div className="mt-2 max-h-56 overflow-y-auto space-y-0.5" role="listbox" aria-label="Tags">
              {isLoading && <Loader2 className="w-4 h-4 m-2 animate-spin text-muted-foreground" />}
              {options.map((tag) => (
                <button key={tag.key} type="button" role="option" aria-selected={false} onClick={() => add(tag.key)}
                  className="w-full flex items-center gap-2 rounded-md px-2 py-1.5 text-sm text-left hover:bg-secondary">
                  <span className={cn("w-2.5 h-2.5 rounded-full shrink-0", TAG_COLOR_DOTS[tag.color] || TAG_COLOR_DOTS.slate)} />
                  <span className="truncate">{tag.name}</span>
                </button>
              ))}
              {canCreate && (
                <button type="button" onClick={create} disabled={createTag.isPending}
                  className="w-full flex items-center gap-2 rounded-md px-2 py-1.5 text-sm text-left hover:bg-secondary text-primary">
                  <TagIcon className="w-3.5 h-3.5 shrink-0" />
                  <span className="truncate">Criar “{term.trim()}”</span>
                </button>
              )}
              {!isLoading && !options.length && !canCreate && (
                <p className="px-2 py-1.5 text-xs text-muted-foreground">
                  {exact ? "O contato já tem esta tag." : "Digite o nome de uma tag nova."}
                </p>
              )}
            </div>
          </PopoverContent>
        </Popover>
      )}
    </div>
  );
}
