import { useEffect, useState, type ComponentType } from "react";
import { createPortal } from "react-dom";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";
import {
  DndContext, DragOverlay, PointerSensor, TouchSensor, pointerWithin, rectIntersection, useDroppable, useSensor, useSensors,
  type CollisionDetection, type DragEndEvent, type DragOverEvent, type DragStartEvent,
} from "@dnd-kit/core";
import { Archive, Check, Columns3, Inbox, List, ListTodo, Loader2, Plus, Search, X } from "lucide-react";
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
import {
  useFunnelBoard, useLeadActions, useSdrQueue, type ArchiveResult, type FunnelFilters, type FunnelLead, type SdrTask,
} from "@/hooks/useFunnel";
import { FunnelBoardView } from "@/components/domain/funnel/FunnelBoardView";
import { FunnelListView } from "@/components/domain/funnel/FunnelListView";
import { LeadCardOverlay } from "@/components/domain/funnel/LeadCard";
import { ArchiveDialog, LostReasonDialog } from "@/components/domain/funnel/LeadDialogs";
import { NewLeadDialog } from "@/components/domain/funnel/NewLeadDialog";
import { LeadDetailsDialog } from "@/components/domain/funnel/LeadDetailsDialog";

const ALL = "__all__";

// Abas do cabeçalho, que também recebem o card arrastado (arquivar / desarquivar)
const DROP_ARCHIVED = "tab:arquivados";
const DROP_ACTIVE = "tab:ativos";
type Tab = "ativos" | "arquivados";

const ARCHIVED_STAGES = ["CONTRACT_SIGNED", "LOST"] as const;
const ARCHIVED_LABELS = { CONTRACT_SIGNED: "Ganho", LOST: "Perdido" };
// Card nestas etapas já tem resultado: arrastar para "Arquivados" (ou o botão do card) arquiva direto
const RESULT_BY_STAGE: Partial<Record<LeadStage, ArchiveResult>> = { CONTRACT_SIGNED: "ganho", LOST: "perdido" };

// Solta onde o ponteiro está (as abas são alvos pequenos); fora delas, a coluna mais sobreposta pelo card.
const collision: CollisionDetection = (args) => {
  const hits = pointerWithin(args);
  return hits.length ? hits : rectIntersection(args);
};

function TabButton({ tab, active, label, icon: Icon, dragging, onSelect }: {
  tab: Tab; active: boolean; label: string; icon: ComponentType<{ className?: string }>; dragging: boolean; onSelect: (tab: Tab) => void;
}) {
  // A aba que não está aberta vira alvo do arrasto: soltar o card nela arquiva ou desarquiva.
  const { setNodeRef, isOver } = useDroppable({ id: tab === "arquivados" ? DROP_ARCHIVED : DROP_ACTIVE, disabled: active });
  const target = dragging && !active;
  return (
    <button ref={setNodeRef} type="button" onClick={() => onSelect(tab)} aria-pressed={active}
      title={tab === "arquivados" ? "Ganhos e perdidos arquivados. Arraste um card até aqui para arquivar" : "Cards em andamento"}
      className={cn("flex items-center gap-1.5 rounded-md px-2.5 py-1 text-sm font-medium transition-all",
        active ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
        target && "outline-dashed outline-2 outline-offset-1 outline-primary/60 text-primary",
        target && isOver && "bg-primary text-primary-foreground outline-primary scale-105")}>
      {/* Rótulo só com espaço no cabeçalho; abaixo disso fica o ícone (o title explica) */}
      <Icon className="w-4 h-4" /><span className="hidden xl:inline">{label}</span>
    </button>
  );
}

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
  const [pendingArchive, setPendingArchive] = useState<FunnelLead | null>(null);
  const [dragging, setDragging] = useState<FunnelLead | null>(null);
  const [overTab, setOverTab] = useState<string | null>(null);
  const [newLeadOpen, setNewLeadOpen] = useState(false);
  // Lead aberto em popup sobre o funil (/funil?lead=<id>, também usado pelos links das outras telas)
  const openLeadId = searchParams.get("lead");
  const view = searchParams.get("view") === "lista" ? "lista" : "quadro";
  const tab: Tab = searchParams.get("arquivados") ? "arquivados" : "ativos";
  const archived = tab === "arquivados";

  useEffect(() => {
    const timer = window.setTimeout(() => setFilters((f) => ({ ...f, search: searchInput.trim() || undefined })), 400);
    return () => window.clearTimeout(timer);
  }, [searchInput]);

  const query = { ...filters, archived };
  const { data: board, isLoading } = useFunnelBoard(query);
  const { data: queue = [] } = useSdrQueue();
  const actions = useLeadActions(null);
  const overdue = queue.filter((t) => isOverdue(t.due_at)).length;
  // Fila do dia: vencidas e com prazo até o fim de hoje. O resto (ex.: reativação em 30 dias) fica em "Próximas".
  const todayLimit = endOfDay(new Date()).getTime();
  const dueToday = queue.filter((t) => new Date(utcIso(t.due_at)).getTime() <= todayLimit);
  const upcoming = queue.filter((t) => new Date(utcIso(t.due_at)).getTime() > todayLimit);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 250, tolerance: 8 } })
  );

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
  const setParam = (key: string, value: string | null) => {
    const params = new URLSearchParams(searchParams);
    if (value) params.set(key, value);
    else params.delete(key);
    setSearchParams(params, { replace: true });
  };
  const setView = (next: "quadro" | "lista") => setParam("view", next === "lista" ? "lista" : null);
  const setTab = (next: Tab) => setParam("arquivados", next === "arquivados" ? "1" : null);

  /** Ganho ou perdido arquiva direto; nas outras etapas pergunta o resultado. */
  const archiveLead = (lead: FunnelLead) => {
    const result = RESULT_BY_STAGE[lead.customer_state_now];
    if (result) actions.archive({ result }, lead.id).catch(() => undefined);
    else setPendingArchive(lead);
  };
  const unarchiveLead = (lead: FunnelLead) => actions.unarchive(lead.id).catch(() => undefined);

  const handleMove = (leadId: string, to: LeadStage) => {
    if (to === "LOST") {
      setPendingLost(leadId);
      return;
    }
    actions.changeStage({ stage: to }, leadId).catch(() => undefined);
  };

  const handleDragStart = (event: DragStartEvent) => setDragging((event.active.data.current?.lead as FunnelLead) ?? null);
  const handleDragOver = (event: DragOverEvent) => setOverTab(
    event.over?.id === DROP_ARCHIVED ? "Solte para arquivar" : event.over?.id === DROP_ACTIVE ? "Solte para desarquivar" : null);
  const handleDragEnd = (event: DragEndEvent) => {
    setDragging(null);
    setOverTab(null);
    const lead = event.active.data.current?.lead as FunnelLead | undefined;
    const over = event.over?.id;
    if (!lead || !over) return;
    if (over === DROP_ARCHIVED) archiveLead(lead);
    else if (over === DROP_ACTIVE) unarchiveLead(lead);
    else if (over !== lead.customer_state_now) handleMove(lead.id, over as LeadStage);
  };

  const stages: readonly LeadStage[] = archived ? ARCHIVED_STAGES : LEAD_STATUS_OPTIONS;
  const totalLeads = board ? stages.reduce((sum, stage) => sum + (board[stage]?.count ?? 0), 0) : 0;
  const filtered = !!(filters.search || filters.product || filters.owner || filters.flag || filters.include_human
    || filters.ai_qualified);

  return (
    <DndContext sensors={sensors} collisionDetection={collision} onDragStart={handleDragStart} onDragOver={handleDragOver}
      onDragEnd={handleDragEnd} onDragCancel={() => { setDragging(null); setOverTab(null); }}>
      <PageShell
        title="Funil de vendas"
        fill={view === "quadro"}
        titleAside={(
          <div className="flex shrink-0 rounded-lg bg-muted p-1" role="group" aria-label="Cards">
            <TabButton tab="ativos" label="Ativos" icon={Inbox} active={!archived} dragging={!!dragging} onSelect={setTab} />
            <TabButton tab="arquivados" label="Arquivados" icon={Archive} active={archived} dragging={!!dragging} onSelect={setTab} />
          </div>
        )}
        actions={(
          <div className="flex items-center gap-2">
            <div className="flex rounded-lg bg-muted p-1" role="group" aria-label="Visualização">
              {([["quadro", "Quadro", Columns3], ["lista", "Lista", List]] as const).map(([key, label, Icon]) => (
                <button key={key} type="button" onClick={() => setView(key)} aria-pressed={view === key} title={label}
                  className={cn("flex items-center gap-1.5 rounded-md px-2.5 py-1 text-sm font-medium transition-colors",
                    view === key ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground")}>
                  <Icon className="w-4 h-4" /><span className="hidden lg:inline">{label}</span>
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
            <span className="text-sm text-muted-foreground whitespace-nowrap"
              title={archived ? "Arraste um card até a aba Ativos para desarquivar" : "Arraste o card para mudar a etapa, ou até a aba Arquivados para arquivar"}>
              {totalLeads} {archived ? "arquivado" : "lead"}{totalLeads === 1 ? "" : "s"}
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
          <div className="glass rounded-2xl border border-border/50 max-h-72 overflow-y-auto pb-1 shrink-0">
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
          <FunnelListView filters={query} onOpen={openLead} />
        ) : isLoading || !board ? (
          <div className="flex justify-center py-20"><Loader2 className="w-6 h-6 animate-spin text-muted-foreground" /></div>
        ) : (
          <FunnelBoardView
            board={board}
            stages={stages}
            labels={archived ? ARCHIVED_LABELS : undefined}
            filters={query}
            onOpen={openLead}
            onAdd={archived ? undefined : () => setNewLeadOpen(true)}
            archivableStages={archived ? [] : ARCHIVED_STAGES}
            onArchive={archived ? undefined : archiveLead}
            onUnarchive={archived ? unarchiveLead : undefined}
          />
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
        <ArchiveDialog
          lead={pendingArchive}
          pending={actions.isPending}
          onClose={() => setPendingArchive(null)}
          onConfirm={(result, lostReason) => {
            const id = pendingArchive?.id;
            setPendingArchive(null);
            if (id) actions.archive({ result, lost_reason: lostReason }, id).catch(() => undefined);
          }}
        />
      </PageShell>
      {/* A cópia do card arrastado vai para o body: fica por cima de colunas, cabeçalho e menus até ser solta */}
      {createPortal(
        <DragOverlay dropAnimation={null} zIndex={60}>{dragging ? <LeadCardOverlay lead={dragging} hint={overTab} /> : null}</DragOverlay>,
        document.body,
      )}
    </DndContext>
  );
}
