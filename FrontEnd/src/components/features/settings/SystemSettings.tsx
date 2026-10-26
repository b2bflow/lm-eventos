import { CalendarDays, Link2, Loader2, RefreshCw, Unplug, Zap } from "lucide-react";
import { toast } from "sonner";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import api from "@/services/api";

interface GoogleStatus {
  client_configured: boolean;
  connected: boolean;
  calendar_id: string;
  auto_sync: boolean;
  last_sync_at: string | null;
  token_from_env: boolean;
}

function errorDetail(error: unknown, fallback: string) {
  return (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail || fallback;
}

/** Aba Integrações: Google Agenda (conectar, sincronizar, pausar a leitura automática e desconectar). */
export function SystemSettings() {
  const queryClient = useQueryClient();
  const { data: google, isLoading } = useQuery({
    queryKey: ["agenda-google-status"],
    queryFn: async () => (await api.get<GoogleStatus>("/agenda/google/status/")).data,
  });
  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["agenda-google-status"] });
    queryClient.invalidateQueries({ queryKey: ["agenda"] });
  };

  const sync = useMutation({
    mutationFn: async () => (await api.post("/agenda/google/sync/")).data,
    onSuccess: () => { toast.success("Agenda sincronizada com o Google."); refresh(); },
    onError: (error) => toast.error(errorDetail(error, "Falha ao sincronizar.")),
  });

  const autoSync = useMutation({
    mutationFn: async (value: boolean) => (await api.patch<GoogleStatus>("/agenda/google/status/", { auto_sync: value })).data,
    onSuccess: (data) => {
      queryClient.setQueryData(["agenda-google-status"], data);
      toast.success(data.auto_sync ? "Sincronização automática ligada." : "Sincronização automática desligada.");
    },
    onError: (error) => toast.error(errorDetail(error, "Não foi possível alterar.")),
  });

  const disconnect = useMutation({
    mutationFn: async () => (await api.post("/agenda/google/disconnect/")).data,
    onSuccess: () => { toast.success("Google Agenda desconectado."); refresh(); },
    onError: (error) => toast.error(errorDetail(error, "Não foi possível desconectar.")),
  });

  const connect = async () => {
    try {
      const { data } = await api.get<{ url: string }>("/agenda/google/connect/");
      window.location.href = data.url;
    } catch (error) {
      toast.error(errorDetail(error, "Não foi possível iniciar a conexão."));
    }
  };

  const confirmDisconnect = () => {
    if (window.confirm("Desconectar o Google Agenda?\n\nO acesso é revogado e os compromissos vindos do Google saem da agenda da plataforma. "
      + "Os agendamentos criados aqui continuam no Google.")) disconnect.mutate();
  };

  if (isLoading || !google) {
    return <div className="flex justify-center p-8"><Loader2 className="animate-spin text-primary w-6 h-6" /></div>;
  }

  const status = google.connected
    ? { tone: "success" as const, label: "Conectado" }
    : google.client_configured
      ? { tone: "warning" as const, label: "Não conectado" }
      : { tone: "danger" as const, label: "Falta o client secret no servidor" };

  return (
    <div className="space-y-6">
      <div className="p-6 rounded-2xl border border-border/50 bg-background/40 backdrop-blur-xl shadow-sm relative overflow-hidden">
        <div className="mb-6 relative z-10 flex flex-wrap items-start justify-between gap-3">
          <div>
            <h3 className="text-lg font-semibold text-foreground flex items-center gap-2">
              <CalendarDays className="w-4 h-4 text-sky-500" /> Google Agenda
            </h3>
            <p className="text-sm text-muted-foreground max-w-xl">
              Espelha a agenda da conta Contato LM na página Agenda e cria no Google as reuniões, visitas e bloqueios agendados aqui.
            </p>
          </div>
          <StatusBadge tone={status.tone}>{status.label}</StatusBadge>
        </div>

        <dl className="relative z-10 grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm mb-6">
          <div>
            <dt className="text-muted-foreground">Agenda</dt>
            <dd className="text-foreground font-medium">{google.calendar_id === "primary" ? "Principal da conta conectada" : google.calendar_id}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Última sincronização</dt>
            <dd className="text-foreground font-medium">{google.last_sync_at ? formatDateTime(google.last_sync_at) : "Ainda não sincronizou"}</dd>
          </div>
        </dl>

        <div className={cn("relative z-10 flex items-center justify-between gap-4 rounded-xl border border-border/50 bg-secondary/30 p-4 mb-6",
          !google.connected && "opacity-60")}>
          <div>
            <Label htmlFor="google-auto-sync" className="font-semibold cursor-pointer">Sincronização automática</Label>
            <p className="text-xs text-muted-foreground">
              Lê o Google a cada 10 minutos. Desligada, a agenda só atualiza pelo botão Sincronizar agora.
            </p>
          </div>
          <Switch id="google-auto-sync" checked={google.auto_sync} disabled={!google.connected || autoSync.isPending}
            onCheckedChange={(value) => autoSync.mutate(value)} />
        </div>

        <div className="relative z-10 flex flex-wrap justify-end gap-2">
          {google.connected ? (
            <>
              <Button variant="outline" onClick={() => sync.mutate()} disabled={sync.isPending}>
                <RefreshCw className={cn("w-4 h-4 mr-2", sync.isPending && "animate-spin")} /> Sincronizar agora
              </Button>
              <Button variant="destructive" onClick={confirmDisconnect} disabled={disconnect.isPending || google.token_from_env}
                title={google.token_from_env ? "A conexão vem da variável GOOGLE_REFRESH_TOKEN do servidor" : undefined}>
                <Unplug className="w-4 h-4 mr-2" /> Desconectar
              </Button>
            </>
          ) : (
            <Button onClick={connect} disabled={!google.client_configured}>
              <Link2 className="w-4 h-4 mr-2" /> Conectar Google Agenda
            </Button>
          )}
        </div>
        {google.token_from_env && (
          <p className="relative z-10 mt-3 text-right text-xs text-muted-foreground">
            Conectado pela variável GOOGLE_REFRESH_TOKEN do servidor: para desconectar, remova-a no Easypanel.
          </p>
        )}
      </div>

      <AiSwitch />
    </div>
  );
}

/** Chave global da IA: desligada, ninguém recebe resposta automática (nem o menu de boas-vindas). */
function AiSwitch() {
  const queryClient = useQueryClient();
  const { data: config } = useQuery({
    queryKey: ["system-config"],
    queryFn: async () => (await api.get<{ ai_active: boolean }>("/chat/configuracoes/")).data,
  });
  const toggle = useMutation({
    // Só ai_active: o backend mantém as demais chaves salvas.
    mutationFn: async (value: boolean) => (await api.post<{ ai_active: boolean }>("/chat/configuracoes/", { ai_active: value })).data,
    onSuccess: (data) => {
      queryClient.setQueryData(["system-config"], data);
      toast.success(data.ai_active ? "IA ligada para todos os atendimentos." : "IA desligada: as mensagens ficam para a equipe.");
    },
    onError: () => toast.error("Não foi possível alterar a IA."),
  });

  return (
    <div className="p-6 rounded-2xl border border-border/50 bg-background/40 backdrop-blur-xl shadow-sm flex flex-wrap items-center justify-between gap-4">
      <div>
        <h3 className="text-lg font-semibold text-foreground flex items-center gap-2">
          <Zap className="w-4 h-4 text-purple-500" /> Inteligência Artificial
        </h3>
        <p className="text-sm text-muted-foreground max-w-xl">
          Desligada, a IA não responde nenhum cliente e o menu de boas-vindas não é enviado: as mensagens chegam no WhatsApp da plataforma para a equipe.
        </p>
      </div>
      <div className="flex items-center gap-2 bg-secondary/30 p-2 rounded-lg border border-border/50">
        <Label htmlFor="ai-active" className="text-xs font-bold cursor-pointer">IA ativa globalmente</Label>
        <Switch id="ai-active" checked={config?.ai_active ?? false} disabled={!config || toggle.isPending}
          onCheckedChange={(value) => toggle.mutate(value)} />
      </div>
    </div>
  );
}
