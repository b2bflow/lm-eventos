import { useEffect, useState } from "react";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { Check, Columns3, List, ListTodo, Loader2, Plus, Search, X } from "lucide-react";
import { endOfDay } from "date-fns";
import { PageShell } from "@/components/shared/PageShell";
import { FilterBar } from "@/components/shared/FilterBar";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { cn } from "@/lib/utils";
import { FLAG_LABELS, LEAD_STATUS_OPTIONS, OWNER_LABELS, PRODUCT_LABELS, type LeadStage } from "@/constants/mappings";
import { formatDateTime, isOverdue, phoneDisplay, utcIso } from "@/lib/format";
import { useFunnelBoard, useLeadActions, useSdrQueue, type FunnelFilters, type SdrTask } from "@/hooks/useFunnel";
import { FunnelBoardView } from "@/components/domain/funnel/FunnelBoardView";
import { FunnelListView } from "@/components/domain/funnel/FunnelListView";
import { LostReasonDialog } from "@/components/domain/funnel/LeadDialogs";
import { NewLeadDialog } from "@/components/domain/funnel/NewLeadDialog";
import { LeadDetailsDialog } from "@/components/domain/funnel/LeadDetailsDialog";

const ALL = "__all__";

function FilterSelect({ value, onChange, placeholder, options }: {
  value?: string; onChange: (v?: string) => void; placeholder: string; options: Record<string, string>;
}) {
  return (
    <Select value={value ?? ALL} onValueChange={(v) => onChange(v === ALL ? undefined : v)}>
      <SelectTrigger className="w-full sm:w-auto sm:min-w-[180px] gap-2"><SelectValue placeholder={placeholder} /></SelectTrigger>
      <SelectContent>
        <SelectItem value={ALL}>{placeholder}</SelectItem>
        {Object.entries(options).map(([key, label]) => <SelectItem key={key} value={key}>{label}</SelectItem>)}
      </SelectContent>
    </Select>
  );
}

function QueueList({ title, tasks, onOpen, onDone }: {
  title: string; tasks: SdrTask[]; onOpen: (id: string) => void; onDone: (taskId: string) => void;
}) {
  if (tasks.length === 0) return null;
  return (
    <div>
      <p className="px-4 pt-3 pb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">{title} ({tasks.length})</p>
      <ul className="divide-y divide-border/50">
        {tasks.map((task) => (
          <li key={task.id} className="flex items-center justify-between gap-2 px-4 py-2 text-sm hover:bg-muted/30">
            <button className="text-left min-w-0 flex-1" onClick={() => onOpen(task.customer_id)}>
              <span className="font-medium text-foreground">{task.label}</span>
              <span className="text-muted-foreground"> · {task.customer_name || phoneDisplay(task.customer_phone)}</span>
              <span className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
                {isOverdue(task.due_at) && <StatusBadge tone="danger">Atrasada</StatusBadge>}
                {formatDateTime(task.due_at)}
              </span>
            </button>
            <Button variant="ghost" size="sm" className="shrink-0" onClick={() => onDone(task.id)} title="Concluir tarefa">
              <Check className="w-4 h-4 sm:mr-1" />
              <span className="hidden sm:inline">Concluir</span>
            </Button>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function Funil() {
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const [filters, setFilters] = useState<FunnelFilters>({});
  const [searchInput, setSearchInput] = useState("");
  const [showQueue, setShowQueue] = useState(false);
  const [pendingLost, setPendingLost] = useState<string | null>(null);
  const [newLeadOpen, setNewLeadOpen] = useState(false);
  // Lead aberto em popup sobre o funil (/funil?lead=<id>, também usado pelos links das outras telas)
  const openLeadId = searchParams.get("lead");
  const view = searchParams.get("view") === "lista" ? "lista" : "quadro";

  useEffect(() => {
    const timer = window.setTimeout(() => setFilters((f) => ({ ...f, search: searchInput.trim() || undefined })), 400);
    return () => window.clearTimeout(timer);
  }, [searchInput]);

  const { data: board, isLoading } = useFunnelBoard(filters);
  const { data: queue = [] } = useSdrQueue();
  const actions = useLeadActions(null);
  const overdue = queue.filter((t) => isOverdue(t.due_at)).length;
  // Fila do dia: vencidas e com prazo até o fim de hoje. O resto (ex.: reativação em 30 dias) fica em "Próximas".
  const todayLimit = endOfDay(new Date()).getTime();
  const dueToday = queue.filter((t) => new Date(utcIso(t.due_at)).getTime() <= todayLimit);
  const upcoming = queue.filter((t) => new Date(utcIso(t.due_at)).getTime() > todayLimit);

  const openLead = (id: string) => {
    const params = new URLSearchParams(searchParams);
    params.set("lead", id);
    setSearchParams(params, { state: { leadPopup: true } });
  };
  const closeLead = () => {
    // Aberto aqui no funil: volta no histórico (o Voltar do navegador também fecha o popup)
    if ((location.state as { leadPopup?: boolean } | null)?.leadPopup) {
      navigate(-1);
      return;
    }
    const params = new URLSearchParams(searchParams);
    params.delete("lead");
    setSearchParams(params, { replace: true });
  };
  const setView = (next: "quadro" | "lista") => {
    const params = new URLSearchParams(searchParams);
    if (next === "lista") params.set("view", "lista");
    else params.delete("view");
    setSearchParams(params, { replace: true });
  };

  const handleMove = (leadId: string, _from: LeadStage, to: LeadStage) => {
    if (to === "LOST") {
      setPendingLost(leadId);
      return;
    }
    actions.changeStage({ stage: to }, leadId).catch(() => undefined);
  };

  const totalLeads = board ? LEAD_STATUS_OPTIONS.reduce((sum, stage) => sum + (board[stage]?.count ?? 0), 0) : 0;
  const filtered = !!(filters.search || filters.product || filters.owner || filters.flag || filters.include_human
    || filters.ai_qualified);

  return (
    <PageShell
      title="Funil de vendas"
      actions={(
        <div className="flex items-center gap-2">
          <div className="flex rounded-lg bg-muted p-1" role="group" aria-label="Visualização">
            {([["quadro", "Quadro", Columns3], ["lista", "Lista", List]] as const).map(([key, label, Icon]) => (
              <button key={key} type="button" onClick={() => setView(key)} aria-pressed={view === key} title={label}
                className={cn("flex items-center gap-1.5 rounded-md px-2.5 py-1 text-sm font-medium transition-colors",
                  view === key ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground")}>
                <Icon className="w-4 h-4" /><span className="hidden md:inline">{label}</span>
              </button>
            ))}
          </div>
          <Button onClick={() => setNewLeadOpen(true)}>
            <Plus className="w-4 h-4 sm:mr-2" />
            <span className="hidden sm:inline">Novo lead</span>
          </Button>
          <Button variant={showQueue ? "default" : "outline"} onClick={() => setShowQueue(!showQueue)}>
            <ListTodo className="w-4 h-4 sm:mr-2" />
            <span className="hidden sm:inline">Fila da SDR</span>
            <span className="ml-1.5 tabular-nums">{dueToday.length}</span>
            {overdue > 0 && <span className="ml-1.5 px-1.5 rounded-full bg-red-600 text-white text-[10px] leading-4">{overdue}</span>}
          </Button>
        </div>
      )}
    >
      <FilterBar
        right={(
          <span className="text-sm text-muted-foreground whitespace-nowrap" title="Arraste o card para mudar a etapa">
            {totalLeads} lead{totalLeads === 1 ? "" : "s"}
          </span>
        )}
      >
        <div className="relative w-full sm:w-auto">
          <Search className="absolute left-2.5 top-2.5 w-4 h-4 text-muted-foreground" />
          <Input value={searchInput} onChange={(e) => setSearchInput(e.target.value)} placeholder="Nome, telefone ou empresa" className="pl-8 w-full sm:w-[260px]" />
        </div>
        <FilterSelect value={filters.product} onChange={(product) => setFilters({ ...filters, product })} placeholder="Todos os produtos" options={PRODUCT_LABELS} />
        <FilterSelect value={filters.owner} onChange={(owner) => setFilters({ ...filters, owner })} placeholder="Todos os responsáveis" options={OWNER_LABELS} />
        <FilterSelect value={filters.flag} onChange={(flag) => setFilters({ ...filters, flag })} placeholder="Todas as sinalizações" options={FLAG_LABELS} />
        <div className="flex items-center gap-2 px-1">
          <Switch id="ai-qualified" checked={!!filters.ai_qualified} onCheckedChange={(v) => setFilters({ ...filters, ai_qualified: v })} />
          <Label htmlFor="ai-qualified" className="text-sm font-normal">Só qualificados pela IA</Label>
        </div>
        <div className="flex items-center gap-2 px-1">
          <Switch id="include-human" checked={!!filters.include_human} onCheckedChange={(v) => setFilters({ ...filters, include_human: v })} />
          <Label htmlFor="include-human" className="text-sm font-normal">Incluir parceiros</Label>
        </div>
        {filtered && (
          <Button variant="ghost" size="sm" onClick={() => { setSearchInput(""); setFilters({}); }}>
            <X className="w-4 h-4 mr-1" /> Limpar
          </Button>
        )}
        {isLoading && <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />}
      </FilterBar>

      {showQueue && (
        <div className="glass rounded-2xl border border-border/50 max-h-72 overflow-y-auto pb-1">
          {queue.length === 0 ? (
            <p className="p-4 text-sm text-muted-foreground">Nenhuma tarefa pendente.</p>
          ) : (
            <>
              {dueToday.length === 0 && <p className="px-4 pt-3 text-sm text-muted-foreground">Nada para hoje.</p>}
              <QueueList title="Para hoje" tasks={dueToday} onOpen={openLead} onDone={(taskId) => actions.completeTask(taskId).catch(() => undefined)} />
              <QueueList title="Próximas" tasks={upcoming} onOpen={openLead} onDone={(taskId) => actions.completeTask(taskId).catch(() => undefined)} />
            </>
          )}
        </div>
      )}

      {view === "lista" ? (
        <FunnelListView filters={filters} onOpen={openLead} />
      ) : isLoading || !board ? (
        <div className="flex justify-center py-20"><Loader2 className="w-6 h-6 animate-spin text-muted-foreground" /></div>
      ) : (
        <FunnelBoardView board={board} filters={filters} onOpen={openLead} onMove={handleMove} onAdd={() => setNewLeadOpen(true)} />
      )}

      <NewLeadDialog open={newLeadOpen} onClose={() => setNewLeadOpen(false)} />
      <LeadDetailsDialog leadId={openLeadId} onClose={closeLead} />
      <LostReasonDialog
        open={!!pendingLost}
        onClose={() => setPendingLost(null)}
        onConfirm={(reason) => {
          const id = pendingLost;
          setPendingLost(null);
          if (id) actions.changeStage({ stage: "LOST", lost_reason: reason }, id).catch(() => undefined);
        }}
      />
    </PageShell>
  );
}
