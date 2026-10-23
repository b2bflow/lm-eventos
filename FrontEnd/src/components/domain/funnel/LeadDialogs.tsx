import { useEffect, useState } from "react";
import { Archive, Trash2, Trophy, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { formatBRL } from "@/lib/format";
import { CALL_OUTCOME_LABELS, LOST_REASON_LABELS } from "@/constants/mappings";
import type { ArchiveResult } from "@/hooks/useFunnel";

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

// Etapas a partir das quais dá para fechar como ganho (contrato assinado exige proposta aceita)
const WON_FROM = ["PROPOSAL_ACCEPTED", "CONTRACT_SIGNED"];

interface ArchiveDialogProps {
  lead: { name?: string | null; phone?: string; customer_state_now: string } | null;
  pending?: boolean;
  onClose: () => void;
  onConfirm: (result: ArchiveResult, lostReason?: string) => void;
}

/** Arquivar um card: escolhe se o lead foi ganho ou perdido (a aba "Arquivados" só tem essas duas colunas). */
export function ArchiveDialog({ lead, pending, onClose, onConfirm }: ArchiveDialogProps) {
  const open = !!lead;
  const stage = lead?.customer_state_now ?? "";
  const canWin = WON_FROM.includes(stage);
  const [result, setResult] = useState<ArchiveResult | null>(null);
  const [reason, setReason] = useState("");
  useEffect(() => {
    setResult(stage === "LOST" ? "perdido" : canWin ? "ganho" : null);
    setReason("");
  }, [open, stage, canWin]);

  const needsReason = result === "perdido" && stage !== "LOST";
  const options: { key: ArchiveResult; label: string; hint: string; icon: typeof Trophy; disabled: boolean; tone: string }[] = [
    {
      key: "ganho", label: "Ganho", icon: Trophy, disabled: !canWin, tone: "border-emerald-500 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
      hint: canWin ? (stage === "CONTRACT_SIGNED" ? "Contrato assinado" : "Registra o contrato assinado") : "Precisa da proposta aceita",
    },
    {
      key: "perdido", label: "Perdido", icon: XCircle, disabled: false, tone: "border-rose-500 bg-rose-500/10 text-rose-700 dark:text-rose-300",
      hint: stage === "LOST" ? "Já marcado como perdido" : "Informe o motivo",
    },
  ];

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Arquivar card</DialogTitle>
          <DialogDescription>
            Como terminou o lead de {lead?.name || lead?.phone || "este contato"}? O card sai do quadro de ativos e fica na
            aba Arquivados; dá para desarquivar depois.
          </DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-2 gap-2" role="radiogroup" aria-label="Resultado">
          {options.map(({ key, label, hint, icon: Icon, disabled, tone }) => (
            <button key={key} type="button" role="radio" aria-checked={result === key} disabled={disabled}
              onClick={() => setResult(key)}
              className={cn("flex flex-col items-center gap-1 rounded-xl border-2 px-3 py-3 text-sm font-semibold transition-colors",
                "disabled:cursor-not-allowed disabled:opacity-50",
                result === key ? tone : "border-border text-foreground hover:bg-secondary")}>
              <Icon className="w-5 h-5" />
              {label}
              <span className="text-[11px] font-normal text-muted-foreground">{hint}</span>
            </button>
          ))}
        </div>
        {needsReason && (
          <div className="space-y-2">
            <Label>Motivo da perda</Label>
            <Select value={reason} onValueChange={setReason}>
              <SelectTrigger><SelectValue placeholder="Selecione o motivo" /></SelectTrigger>
              <SelectContent>
                {Object.entries(LOST_REASON_LABELS).map(([key, label]) => <SelectItem key={key} value={key}>{label}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancelar</Button>
          <Button disabled={!result || (needsReason && !reason) || pending}
            onClick={() => result && onConfirm(result, needsReason ? reason : undefined)}>
            <Archive className="w-4 h-4 mr-1.5" /> Arquivar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

interface DeleteProposalDialogProps {
  proposal: { version: number; total: number; sent_at: string | null } | null;
  /** Versão anterior que volta a ser a atual (a excluída era a atual e a anterior estava substituída). */
  restoresVersion?: number | null;
  pending?: boolean;
  onClose: () => void;
  onConfirm: () => void;
}

export function DeleteProposalDialog({ proposal, restoresVersion, pending, onClose, onConfirm }: DeleteProposalDialogProps) {
  return (
    <Dialog open={!!proposal} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Excluir proposta v{proposal?.version}</DialogTitle>
          <DialogDescription asChild>
            <div className="space-y-2">
              <p>
                A proposta de {proposal ? formatBRL(proposal.total) : ""} e o PDF dela são apagados do banco de vez. Não dá
                para desfazer.
              </p>
              {proposal?.sent_at && <p>Ela já foi enviada: o link do PDF que o cliente recebeu deixa de abrir.</p>}
              {restoresVersion && <p>A v{restoresVersion} volta a ser a proposta atual do card.</p>}
            </div>
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancelar</Button>
          <Button variant="destructive" disabled={pending} onClick={onConfirm}>
            <Trash2 className="w-4 h-4 mr-1.5" /> Excluir proposta
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
