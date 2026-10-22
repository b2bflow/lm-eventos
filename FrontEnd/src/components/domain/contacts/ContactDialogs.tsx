import { useEffect, useState } from "react";
import { FileUp, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { CONTACT_TYPE_LABELS, ORIGIN_LABELS } from "@/constants/mappings";
import { phoneDisplay } from "@/lib/format";
import { errorDetail, useCreateContact, useImportPartners, type ImportResult } from "@/hooks/useContacts";

const NONE = "__none__";

export function NewContactDialog({ open, onClose, onCreated, initial }: {
  open: boolean; onClose: () => void; onCreated: (id: string) => void;
  /** Pré-preenche o formulário (ex.: o que foi digitado na busca da calculadora). */
  initial?: { name?: string; phone?: string };
}) {
  const create = useCreateContact();
  const [form, setForm] = useState({ name: "", phone: "", email: "", company: "", role: "", contact_type: "lead", origin: "" });
  const [partner, setPartner] = useState(false);
  const [duplicateId, setDuplicateId] = useState<string | null>(null);

  useEffect(() => {
    if (open && initial) setForm((f) => ({ ...f, name: initial.name || f.name, phone: initial.phone || f.phone }));
  }, [open, initial]);

  const reset = () => {
    setForm({ name: "", phone: "", email: "", company: "", role: "", contact_type: "lead", origin: "" });
    setPartner(false);
    setDuplicateId(null);
  };

  const submit = () => {
    setDuplicateId(null);
    create.mutate(
      { ...form, origin: form.origin || null, human_operator: partner },
      {
        onSuccess: (contact) => {
          reset();
          onCreated(contact.id);
        },
        onError: (error) => {
          const existing = (error as { response?: { data?: { existing_id?: string } } })?.response?.data?.existing_id;
          if (existing) setDuplicateId(existing);
          toast.error(errorDetail(error, "Não foi possível cadastrar o contato."));
        },
      },
    );
  };

  const field = (key: keyof typeof form, label: string, props: React.InputHTMLAttributes<HTMLInputElement> = {}) => (
    <div className="space-y-1">
      <Label htmlFor={`new-${key}`}>{label}</Label>
      <Input id={`new-${key}`} value={form[key]} onChange={(e) => setForm({ ...form, [key]: e.target.value })} {...props} />
    </div>
  );

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) { reset(); onClose(); } }}>
      <DialogContent className="sm:max-w-lg max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Novo contato</DialogTitle>
          <DialogDescription>O telefone não pode repetir: o mesmo número com ou sem o 9 é o mesmo contato.</DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {field("phone", "Telefone *", { placeholder: "(62) 99999-1111", inputMode: "tel" })}
          {field("name", "Nome")}
          {field("company", "Empresa")}
          {field("role", "Cargo")}
          {field("email", "E-mail", { type: "email" })}
          <div className="space-y-1">
            <Label>Tipo</Label>
            <Select value={form.contact_type} onValueChange={(v) => setForm({ ...form, contact_type: v })}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {Object.entries(CONTACT_TYPE_LABELS).map(([k, l]) => <SelectItem key={k} value={k}>{l}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label>Origem</Label>
            <Select value={form.origin || NONE} onValueChange={(v) => setForm({ ...form, origin: v === NONE ? "" : v })}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value={NONE}>Não informada</SelectItem>
                {Object.entries(ORIGIN_LABELS).map(([k, l]) => <SelectItem key={k} value={k}>{l}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="flex items-center gap-2 sm:pt-6">
            <Switch id="new-partner" checked={partner} onCheckedChange={setPartner} />
            <Label htmlFor="new-partner">Parceiro (fica com a Erica)</Label>
          </div>
        </div>
        {duplicateId && (
          <Button variant="link" className="px-0 justify-start" onClick={() => { reset(); onCreated(duplicateId); }}>
            Abrir o contato que já existe
          </Button>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={() => { reset(); onClose(); }}>Cancelar</Button>
          <Button disabled={!form.phone.trim() || create.isPending} onClick={submit}>
            {create.isPending && <Loader2 className="w-4 h-4 mr-1 animate-spin" />} Cadastrar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

const ACTION_LABELS: Record<string, string> = {
  created: "Novo parceiro",
  updated: "Vira parceiro",
  unchanged: "Já é parceiro",
};

function ImportSummary({ result }: { result: ImportResult }) {
  return (
    <div className="space-y-3 text-sm">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        {[
          ["Novos", result.created],
          ["Viram parceiro", result.updated],
          ["Já eram", result.unchanged],
          ["Inválidos", result.invalid.length],
        ].map(([label, value]) => (
          <div key={label as string} className="rounded-lg border p-2 text-center">
            <p className="text-lg font-bold">{value}</p>
            <p className="text-xs text-muted-foreground">{label}</p>
          </div>
        ))}
      </div>
      {result.repeated > 0 && <p className="text-xs text-muted-foreground">{result.repeated} número(s) repetido(s) no arquivo foram ignorados.</p>}
      {result.invalid.length > 0 && (
        <ul className="text-xs text-rose-600 list-disc pl-4 max-h-24 overflow-y-auto">
          {result.invalid.map((row) => <li key={row.line}>Linha {row.line}: "{row.value}" ({row.reason})</li>)}
        </ul>
      )}
      {result.rows.length > 0 && (
        <ul className="divide-y rounded-lg border max-h-48 overflow-y-auto">
          {result.rows.map((row) => (
            <li key={row.line} className="flex items-center justify-between gap-2 px-3 py-1.5 text-xs">
              <span className="min-w-0 truncate">
                {phoneDisplay(row.phone)} · {row.name || row.existing_name || "sem nome"}
              </span>
              <span className="shrink-0 text-muted-foreground">{ACTION_LABELS[row.action] || row.action}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function ImportPartnersDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const importer = useImportPartners();
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportResult | null>(null);
  const [done, setDone] = useState<ImportResult | null>(null);

  const close = () => {
    setFile(null);
    setPreview(null);
    setDone(null);
    onClose();
  };

  const check = (selected: File) => {
    setFile(selected);
    setPreview(null);
    setDone(null);
    importer.mutate({ file: selected, dryRun: true }, { onSuccess: setPreview });
  };

  const confirm = () => {
    if (!file) return;
    importer.mutate({ file, dryRun: false }, {
      onSuccess: (result) => {
        setDone(result);
        toast.success(`${result.created + result.updated} contato(s) marcados como parceiro.`);
      },
    });
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && close()}>
      <DialogContent className="sm:max-w-lg max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Importar lista de parceiros</DialogTitle>
          <DialogDescription>
            CSV com uma coluna de telefone (e, se quiser, uma de nome). Os números viram parceiros: ficam com a Erica,
            não entram na fila da SDR e a assistente virtual não responde. Nada muda antes de você confirmar.
          </DialogDescription>
        </DialogHeader>

        <label className="flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed p-6 text-sm cursor-pointer hover:bg-secondary/40">
          <FileUp className="w-6 h-6 text-muted-foreground" />
          <span>{file ? file.name : "Escolher arquivo .csv"}</span>
          <input
            type="file"
            accept=".csv,.txt,text/csv,text/plain"
            className="sr-only"
            onChange={(e) => {
              const selected = e.target.files?.[0];
              if (selected) check(selected);
              e.target.value = "";
            }}
          />
        </label>

        {importer.isPending && <div className="flex justify-center"><Loader2 className="w-5 h-5 animate-spin" /></div>}
        {done ? (
          <>
            <p className="text-sm font-medium text-emerald-600">Importação concluída.</p>
            <ImportSummary result={done} />
          </>
        ) : preview && (
          <>
            <p className="text-sm font-medium">Conferência ({preview.total} linha(s) lidas):</p>
            <ImportSummary result={preview} />
          </>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={close}>{done ? "Fechar" : "Cancelar"}</Button>
          {!done && (
            <Button disabled={!preview || importer.isPending || preview.created + preview.updated === 0} onClick={confirm}>
              Confirmar importação
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
