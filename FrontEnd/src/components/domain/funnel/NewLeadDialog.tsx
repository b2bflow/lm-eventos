import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, UserRound, X } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import api from "@/services/api";
import { phoneDisplay } from "@/lib/format";
import { PRODUCT_LABELS } from "@/constants/mappings";
import { errorDetail } from "@/hooks/useContacts";
import { ContactPicker } from "@/components/domain/contacts/ContactPicker";

type PickedContact = { id: string; name?: string | null; phone?: string };

/**
 * Abre um lead no funil para um contato (Novo lead no Funil, Converter em lead no WhatsApp).
 * Sem `contact`, o diálogo começa pela busca do contato, com cadastro rápido.
 */
export function NewLeadDialog({ open, onClose, contact }: {
  open: boolean;
  onClose: () => void;
  contact?: PickedContact | null;
}) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [picked, setPicked] = useState<PickedContact | null>(contact ?? null);
  const [product, setProduct] = useState("");

  // Recomeça ao abrir (ou trocar de contato); `contact` costuma ser um objeto novo a cada render.
  const contactId = contact?.id;
  useEffect(() => {
    if (open) {
      setPicked(contact ?? null);
      setProduct("");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, contactId]);

  const create = useMutation({
    mutationFn: async () => (await api.post(`/crm/contacts/${picked?.id}/new-lead/`, { product })).data,
    onSuccess: () => {
      toast.success("Lead aberto no funil.");
      queryClient.invalidateQueries({ queryKey: ["funnel"] });
      queryClient.invalidateQueries({ queryKey: ["contacts"] });
      queryClient.invalidateQueries({ queryKey: ["conversations"] });
      onClose();
      navigate(`/funil?lead=${picked?.id}`);
    },
    onError: (error) => toast.error(errorDetail(error, "Não foi possível abrir o lead.")),
  });

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{contact ? "Converter em lead" : "Novo lead"}</DialogTitle>
          <DialogDescription>O lead entra no funil como Lead qualificado. Um lead antigo em aberto vai para o histórico do contato.</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-1">
            <Label>Contato</Label>
            {picked ? (
              <div className="flex items-center gap-3 rounded-xl border border-border/60 bg-card px-3 py-2">
                <span className="w-8 h-8 rounded-full bg-primary/10 text-primary grid place-items-center shrink-0"><UserRound className="w-4 h-4" /></span>
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-semibold text-foreground truncate">{picked.name || "Contato selecionado"}</span>
                  {picked.phone && <span className="block text-xs text-muted-foreground">{phoneDisplay(picked.phone)}</span>}
                </span>
                {!contact && (
                  <Button variant="ghost" size="icon" className="h-7 w-7 shrink-0" title="Trocar contato" onClick={() => setPicked(null)}>
                    <X className="w-4 h-4" />
                  </Button>
                )}
              </div>
            ) : (
              <ContactPicker className="sm:w-full" autoFocus onPick={setPicked} />
            )}
          </div>
          <div className="space-y-1">
            <Label>Produto</Label>
            <Select value={product} onValueChange={setProduct}>
              <SelectTrigger><SelectValue placeholder="Escolha o produto" /></SelectTrigger>
              <SelectContent>
                {Object.entries(PRODUCT_LABELS).map(([key, label]) => <SelectItem key={key} value={key}>{label}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancelar</Button>
          <Button disabled={!picked || !product || create.isPending} onClick={() => create.mutate()}>
            {create.isPending && <Loader2 className="w-4 h-4 mr-1 animate-spin" />} Abrir lead
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
