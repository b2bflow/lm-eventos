import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Loader2, Search, UserPlus } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Popover, PopoverAnchor, PopoverContent } from "@/components/ui/popover";
import api from "@/services/api";
import { cn } from "@/lib/utils";
import { phoneDisplay } from "@/lib/format";
import { LEAD_STATUS_LABELS, PRODUCT_LABELS, resolveStage } from "@/constants/mappings";
import type { ContactSummary } from "@/hooks/useContacts";
import { NewContactDialog } from "./ContactDialogs";

function useDebounced<T>(value: T, delay: number) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = window.setTimeout(() => setDebounced(value), delay);
    return () => window.clearTimeout(t);
  }, [value, delay]);
  return debounced;
}

/** O que foi digitado vira telefone (só números e símbolos) ou nome no cadastro rápido. */
function initialFromTerm(term: string) {
  const digits = term.replace(/\D/g, "");
  return digits.length >= 8 && !/[a-zà-ú]/i.test(term) ? { phone: term } : { name: term };
}

/**
 * Busca de contato por nome ou telefone com cadastro rápido quando não encontra.
 * A lista abre num portal (por cima dos cartões com `backdrop-filter`, que criam camadas próprias).
 */
export function ContactPicker({ onPick, placeholder = "Buscar cliente (nome ou telefone)", className, autoFocus }: {
  onPick: (contact: { id: string; name?: string | null; phone?: string }) => void;
  placeholder?: string;
  className?: string;
  autoFocus?: boolean;
}) {
  const [term, setTerm] = useState("");
  const [open, setOpen] = useState(false);
  // Dados do cadastro rápido (nulo = diálogo fechado). Fica em estado para não mudar a cada render.
  const [creating, setCreating] = useState<{ name?: string; phone?: string } | null>(null);
  const search = useDebounced(term.trim(), 300);
  const { data = [], isFetching } = useQuery({
    queryKey: ["contact-picker", search],
    queryFn: async () => (await api.get("/crm/contacts/", { params: { search, page_size: 8 } })).data.results as ContactSummary[],
    enabled: search.length >= 2,
  });
  const show = open && search.length >= 2;

  const pick = (contact: { id: string; name?: string | null; phone?: string }) => {
    setOpen(false);
    setTerm("");
    onPick(contact);
  };

  return (
    <>
      <Popover open={show} onOpenChange={setOpen}>
        <PopoverAnchor asChild>
          <div className={cn("relative w-full sm:w-[320px]", className)}>
            <Search className="absolute left-2.5 top-2.5 w-4 h-4 text-muted-foreground" />
            <Input value={term} autoFocus={autoFocus} placeholder={placeholder} className="pl-8"
              onChange={(e) => { setTerm(e.target.value); setOpen(true); }} onFocus={() => setOpen(true)} />
            {isFetching && <Loader2 className="absolute right-2.5 top-2.5 w-4 h-4 animate-spin text-muted-foreground" />}
          </div>
        </PopoverAnchor>
        <PopoverContent align="start" className="p-0 w-[var(--radix-popover-trigger-width)] min-w-[280px] max-h-72 overflow-y-auto"
          onOpenAutoFocus={(e) => e.preventDefault()}
          onInteractOutside={(e) => {
            // Clicar no próprio campo não fecha a lista
            if ((e.target as HTMLElement | null)?.closest?.("input") === document.activeElement) e.preventDefault();
          }}>
          <ul className="divide-y divide-border/50">
            {data.length === 0 && !isFetching && (
              <li className="px-3 py-2 text-sm text-muted-foreground">Nenhum contato encontrado.</li>
            )}
            {data.map((contact) => (
              <li key={contact.id}>
                <button type="button" className="w-full text-left px-3 py-2 text-sm hover:bg-muted/60" onClick={() => pick(contact)}>
                  <span className="font-medium text-foreground">{contact.name || "Sem nome"}</span>
                  <span className="text-muted-foreground"> · {phoneDisplay(contact.phone)}</span>
                  {contact.current_lead && (
                    <span className="block text-xs text-muted-foreground">
                      {contact.current_lead.product ? `${PRODUCT_LABELS[contact.current_lead.product] || contact.current_lead.product} · ` : ""}
                      {LEAD_STATUS_LABELS[resolveStage(contact.current_lead.stage)]}
                    </span>
                  )}
                </button>
              </li>
            ))}
            <li>
              <button type="button" className="w-full flex items-center gap-2 px-3 py-2 text-sm font-medium text-primary hover:bg-primary/5"
                onClick={() => { setOpen(false); setCreating(initialFromTerm(search)); }}>
                <UserPlus className="w-4 h-4" /> Criar contato «{search}»
              </button>
            </li>
          </ul>
        </PopoverContent>
      </Popover>
      <NewContactDialog open={!!creating} initial={creating ?? undefined}
        onClose={() => setCreating(null)}
        onCreated={(id) => { setCreating(null); pick({ id }); }} />
    </>
  );
}
