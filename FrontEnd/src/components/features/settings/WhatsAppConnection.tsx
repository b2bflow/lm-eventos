import { useEffect, useState } from "react";
import { AlertCircle, CheckCircle2, Link2, Loader2, QrCode, RefreshCw, Smartphone, Unplug } from "lucide-react";
import { toast } from "sonner";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription,
  AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { phoneDisplay } from "@/lib/format";
import api from "@/services/api";

type ZapiState = "connected" | "disconnected" | "unreachable" | "not_configured";

interface ZapiStatus {
  state: ZapiState;
  connected: boolean;
  smartphone_connected: boolean | null;
  phone: string | null;
  name: string | null;
  qr_code: string | null; // data URI, pronto para <img src>
  error: string | null;
}

// O WhatsApp troca o QR Code a cada ~20 s: enquanto alguém conecta, a tela pede um novo a cada 15 s.
const QR_REFRESH_MS = 15_000;
// Depois disso sem escanear, para de pedir QR (a Z-API também desiste de gerar após várias tentativas).
const QR_GIVE_UP_MS = 5 * 60_000;

function errorDetail(error: unknown, fallback: string) {
  return (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail || fallback;
}

const BADGES: Record<ZapiState, { label: string; className: string }> = {
  connected: { label: "Conectado", className: "bg-green-500/10 text-green-600 border-green-500/20" },
  disconnected: { label: "Desconectado", className: "bg-red-500/10 text-red-600 border-red-500/20" },
  unreachable: { label: "Sem resposta", className: "bg-amber-500/10 text-amber-600 border-amber-500/20" },
  not_configured: { label: "Não configurado", className: "bg-secondary text-muted-foreground border-border" },
};

/** API's: conexão do número de WhatsApp da LM na Z-API (status, conectar pelo QR Code e desconectar). */
export function WhatsAppConnection() {
  const queryClient = useQueryClient();
  const [connecting, setConnecting] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);

  const { data, isLoading, isFetching, refetch } = useQuery({
    queryKey: ["zapi-status", connecting],
    queryFn: async () => (await api.get<ZapiStatus>("/gateway/zapi/status/", { params: connecting ? { qr: 1 } : {} })).data,
    placeholderData: keepPreviousData,
    refetchInterval: connecting ? QR_REFRESH_MS : 60_000,
    refetchIntervalInBackground: false,
  });

  // Escaneou: sai do modo QR e avisa.
  useEffect(() => {
    if (connecting && data?.state === "connected") {
      setConnecting(false);
      toast.success("WhatsApp conectado.");
    }
  }, [connecting, data?.state]);

  useEffect(() => {
    if (!connecting) return;
    const timer = window.setTimeout(() => {
      setConnecting(false);
      toast.info("O QR Code expirou. Clique em Conectar para gerar outro.");
    }, QR_GIVE_UP_MS);
    return () => window.clearTimeout(timer);
  }, [connecting]);

  const disconnect = useMutation({
    mutationFn: async () => (await api.post<ZapiStatus>("/gateway/zapi/disconnect/")).data,
    onSuccess: (snapshot) => {
      queryClient.setQueryData(["zapi-status", false], snapshot);
      setConfirmOpen(false);
      toast.success("WhatsApp desconectado.");
      // A Z-API pode levar uns segundos para refletir a desconexão no /status.
      window.setTimeout(() => queryClient.invalidateQueries({ queryKey: ["zapi-status"] }), 3000);
    },
    onError: (error) => toast.error(errorDetail(error, "Não foi possível desconectar.")),
  });

  const state: ZapiState | undefined = data?.state;
  const badge = state ? BADGES[state] : null;
  const showQr = connecting && state === "disconnected";

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h3 className="text-lg font-semibold text-foreground">API's</h3>
          <p className="text-sm text-muted-foreground">Conexão do número de WhatsApp da LM (Z-API).</p>
        </div>
        <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
          <RefreshCw className={`w-4 h-4 mr-2 ${isFetching ? "animate-spin" : ""}`} />
          Atualizar
        </Button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="p-4 sm:p-6 rounded-2xl border border-border/50 bg-background/40 backdrop-blur-xl shadow-sm">
          <div className="flex items-start justify-between gap-3">
            <div className="flex items-center gap-2 min-w-0">
              <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center shrink-0">
                <Smartphone className="w-5 h-5 text-primary" />
              </div>
              <div className="min-w-0">
                <p className="font-semibold text-foreground truncate">{data?.name || "WhatsApp da LM"}</p>
                <p className="text-xs text-muted-foreground truncate">
                  {data?.phone ? phoneDisplay(data.phone) : "WhatsApp Business (Z-API)"}
                </p>
              </div>
            </div>
            {isLoading ? (
              <Loader2 className="w-4 h-4 animate-spin text-muted-foreground shrink-0" />
            ) : badge && (
              <Badge variant="outline" className={`${badge.className} shrink-0`}>
                {state === "connected" && <CheckCircle2 className="w-3 h-3 mr-1" />}
                {badge.label}
              </Badge>
            )}
          </div>

          {state === "connected" && (
            <div className="mt-4 pt-4 border-t border-border/50 flex items-center justify-between gap-3 flex-wrap">
              <p className="text-xs text-muted-foreground flex-1 min-w-[12rem]">
                {data?.smartphone_connected === false
                  ? "Conectado, mas o celular está sem internet: as mensagens podem atrasar."
                  : "A IA e o painel enviam e recebem mensagens por este número."}
              </p>
              <Button variant="outline" size="sm" onClick={() => setConfirmOpen(true)}
                className="text-red-600 border-red-500/30 hover:bg-red-500/10 hover:text-red-600">
                <Unplug className="w-4 h-4 mr-2" /> Desconectar
              </Button>
            </div>
          )}

          {state === "disconnected" && !connecting && (
            <div className="mt-4 pt-4 border-t border-border/50 flex items-center justify-between gap-3 flex-wrap">
              <p className="text-xs text-muted-foreground flex-1 min-w-[12rem]">
                Sem WhatsApp conectado, a IA e o painel não recebem nem enviam mensagens.
              </p>
              <Button size="sm" onClick={() => setConnecting(true)}>
                <Link2 className="w-4 h-4 mr-2" /> Conectar
              </Button>
            </div>
          )}

          {showQr && (
            <div className="mt-4 pt-4 border-t border-border/50 flex flex-col items-center gap-3">
              {data?.qr_code ? (
                <img src={data.qr_code} alt="QR Code para conectar o WhatsApp da LM"
                  className="w-48 h-48 rounded-lg border border-border/50 bg-white p-2" />
              ) : data?.error ? (
                <p className="text-xs text-red-500 text-center flex items-center gap-1 py-6">
                  <AlertCircle className="w-3.5 h-3.5 shrink-0" /> {data.error}
                </p>
              ) : (
                <div className="w-48 h-48 rounded-lg border border-dashed border-border flex flex-col items-center justify-center gap-2 text-xs text-muted-foreground">
                  <Loader2 className="w-5 h-5 animate-spin text-primary" /> Gerando QR Code…
                </div>
              )}
              <ol className="text-xs text-muted-foreground list-decimal pl-4 space-y-0.5 self-stretch">
                <li>Abra o WhatsApp no celular do número da LM.</li>
                <li>Toque em <b>⋮</b> (ou Configurações) &gt; <b>Aparelhos conectados</b> &gt; <b>Conectar um aparelho</b>.</li>
                <li>Aponte a câmera para este código.</li>
              </ol>
              <div className="flex items-center justify-between gap-2 self-stretch">
                <p className="text-[11px] text-muted-foreground flex items-center gap-1">
                  <QrCode className="w-3.5 h-3.5 shrink-0" /> O código se renova sozinho.
                </p>
                <Button variant="ghost" size="sm" onClick={() => setConnecting(false)}>Cancelar</Button>
              </div>
            </div>
          )}

          {(state === "unreachable" || state === "not_configured") && data?.error && (
            <p className="mt-4 pt-4 border-t border-border/50 text-xs text-red-500 flex items-start gap-1">
              <AlertCircle className="w-3.5 h-3.5 shrink-0 mt-0.5" /> {data.error}
            </p>
          )}
        </div>
      </div>

      <AlertDialog open={confirmOpen} onOpenChange={(open) => { if (!disconnect.isPending) setConfirmOpen(open); }}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Desconectar o WhatsApp?</AlertDialogTitle>
            <AlertDialogDescription>
              O número {data?.phone ? phoneDisplay(data.phone) : "da LM"} sai dos aparelhos conectados. Até conectar de novo
              pelo QR Code, a IA e o painel não recebem nem enviam mensagens (o que chegar nesse tempo fica só no celular).
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={disconnect.isPending}>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              disabled={disconnect.isPending}
              onClick={(e) => { e.preventDefault(); disconnect.mutate(); }}
            >
              {disconnect.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : "Desconectar"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
