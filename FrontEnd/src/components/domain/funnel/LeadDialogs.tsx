import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { CALL_OUTCOME_LABELS, LOST_REASON_LABELS } from "@/constants/mappings";

interface LostReasonDialogProps {
  open: boolean;
  onClose: () => void;
  onConfirm: (reason: string) => void;
}

export function LostReasonDialog({ open, onClose, onConfirm }: LostReasonDialogProps) {
  const [reason, setReason] = useState("");
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Marcar como perdido</DialogTitle>
        </DialogHeader>
        <div className="space-y-2">
          <Label>Motivo</Label>
          <Select value={reason} onValueChange={setReason}>
            <SelectTrigger>
              <SelectValue placeholder="Selecione o motivo" />
            </SelectTrigger>
            <SelectContent>
              {Object.entries(LOST_REASON_LABELS).map(([key, label]) => (
                <SelectItem key={key} value={key}>{label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancelar</Button>
          <Button
            variant="destructive"
            disabled={!reason}
            onClick={() => {
              onConfirm(reason);
              setReason("");
            }}
          >
            Marcar perdido
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

interface CallDialogProps {
  open: boolean;
  onClose: () => void;
  onConfirm: (outcome: string, notes: string) => void;
}

export function CallDialog({ open, onClose, onConfirm }: CallDialogProps) {
  const [outcome, setOutcome] = useState("");
  const [notes, setNotes] = useState("");
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Registrar ligação</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-2">
            <Label>Resultado</Label>
            <Select value={outcome} onValueChange={setOutcome}>
              <SelectTrigger>
                <SelectValue placeholder="Como foi a ligação?" />
              </SelectTrigger>
              <SelectContent>
                {Object.entries(CALL_OUTCOME_LABELS).map(([key, label]) => (
                  <SelectItem key={key} value={key}>{label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label>Observações</Label>
            <Textarea value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="O que foi combinado" />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancelar</Button>
          <Button
            disabled={!outcome}
            onClick={() => {
              onConfirm(outcome, notes);
              setOutcome("");
              setNotes("");
            }}
          >
            Registrar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

interface RemoveFromFunnelDialogProps {
  open: boolean;
  name: string;
  pending?: boolean;
  onClose: () => void;
  onConfirm: () => void;
}

export function RemoveFromFunnelDialog({ open, name, pending, onClose, onConfirm }: RemoveFromFunnelDialogProps) {
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Excluir do funil</DialogTitle>
          <DialogDescription>
            O card de {name} sai do quadro e as tarefas pendentes da SDR são canceladas. O contato, a conversa,
            as propostas e o histórico continuam na página Contatos, e dá para abrir um lead novo por lá.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancelar</Button>
          <Button variant="destructive" disabled={pending} onClick={onConfirm}>Excluir do funil</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
