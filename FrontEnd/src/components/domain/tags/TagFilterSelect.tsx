import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { cn } from "@/lib/utils";
import { TAG_COLOR_DOTS, useTags } from "@/hooks/useTags";

const ALL = "__all__";

/** Filtro "Todas as tags" / uma tag do catálogo. `value` é a chave da tag ("" ou undefined = todas). */
export function TagFilterSelect({ value, onChange, triggerClassName }: {
  value?: string;
  onChange: (key: string | undefined) => void;
  triggerClassName?: string;
}) {
  const { data: tags = [] } = useTags();
  const sorted = [...tags].sort((a, b) => a.name.localeCompare(b.name, "pt-BR"));
  // Tag do link que não existe mais (excluída): continua selecionada até trocar.
  const missing = value && !tags.some((tag) => tag.key === value);
  return (
    <Select value={value || ALL} onValueChange={(v) => onChange(v === ALL ? undefined : v)}>
      <SelectTrigger className={cn(triggerClassName)} aria-label="Tag"><SelectValue /></SelectTrigger>
      <SelectContent>
        <SelectItem value={ALL}>Todas as tags</SelectItem>
        {missing && <SelectItem value={value}>{value}</SelectItem>}
        {sorted.map((tag) => (
          <SelectItem key={tag.key} value={tag.key}>
            <span className="flex items-center gap-2">
              <span className={cn("w-2 h-2 rounded-full shrink-0", TAG_COLOR_DOTS[tag.color] || TAG_COLOR_DOTS.slate)} />
              {tag.name}
            </span>
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
