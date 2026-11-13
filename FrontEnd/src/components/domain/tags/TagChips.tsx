import { X } from "lucide-react";
import { cn } from "@/lib/utils";
import { TAG_COLOR_STYLES, useTagMap, type CustomerTag } from "@/hooks/useTags";

export function TagChip({ tagKey, tag, onRemove, className, removing }: {
  tagKey: string;
  tag?: CustomerTag;
  onRemove?: () => void;
  removing?: boolean;
  className?: string;
}) {
  const name = tag?.name || tagKey;
  return (
    <span className={cn(
      "inline-flex items-center gap-1 max-w-full rounded-full border px-2 py-0.5 text-[11px] font-semibold leading-4",
      TAG_COLOR_STYLES[tag?.color || "slate"] || TAG_COLOR_STYLES.slate, className,
    )}>
      <span className="truncate">{name}</span>
      {onRemove && (
        <button type="button" onClick={(e) => { e.stopPropagation(); onRemove(); }} disabled={removing}
          aria-label={`Tirar a tag ${name}`} title={`Tirar a tag ${name}`}
          className="-mr-0.5 rounded-full p-0.5 opacity-70 hover:opacity-100 hover:bg-black/10 disabled:opacity-40">
          <X className="w-3 h-3" />
        </button>
      )}
    </span>
  );
}

/** Tags do cliente, só para leitura (lista de conversas, contatos, CRM). */
export function TagChips({ tags, max, className, chipClassName }: {
  tags?: string[] | null;
  max?: number;
  className?: string;
  chipClassName?: string;
}) {
  const catalog = useTagMap();
  if (!tags?.length) return null;
  const shown = max ? tags.slice(0, max) : tags;
  const hidden = tags.length - shown.length;
  return (
    <span className={cn("flex flex-wrap items-center gap-1", className)}>
      {shown.map((key) => <TagChip key={key} tagKey={key} tag={catalog.get(key)} className={chipClassName} />)}
      {hidden > 0 && (
        <span className="text-[10px] font-semibold text-muted-foreground"
          title={tags.slice(shown.length).map((key) => catalog.get(key)?.name || key).join(", ")}>
          +{hidden}
        </span>
      )}
    </span>
  );
}
