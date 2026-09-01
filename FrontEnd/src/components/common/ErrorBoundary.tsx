import React, { Component, ErrorInfo, ReactNode } from "react";
import { AlertTriangle, RefreshCw, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
  isAutoReloading: boolean;
}

const AUTO_RELOAD_INTERVAL_MS = 15000; // 15 segundos para evitar loop infinito de reload

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
    isAutoReloading: false,
  };

  public static getDerivedStateFromError(error: Error): State {
    const lastReloadStr = sessionStorage.getItem("last_auto_reload_ts");
    const lastReload = lastReloadStr ? parseInt(lastReloadStr, 10) : 0;
    const now = Date.now();

    const shouldAutoReload = now - lastReload > AUTO_RELOAD_INTERVAL_MS;

    return {
      hasError: true,
      error,
      isAutoReloading: shouldAutoReload,
    };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("[ErrorBoundary caught an error]:", error, errorInfo);

    if (this.state.isAutoReloading) {
      sessionStorage.setItem("last_auto_reload_ts", String(Date.now()));
      // Recarrega automaticamente sem perguntar ao usuário
      window.location.reload();
    }
  }

  private handleManualReset = () => {
    this.setState({ hasError: false, error: null, isAutoReloading: false });
    sessionStorage.removeItem("last_auto_reload_ts");
    window.location.reload();
  };

  public render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      // Se estiver no processo de recarregamento automático
      if (this.state.isAutoReloading) {
        return (
          <div className="flex h-screen w-full flex-col items-center justify-center bg-background p-6 text-foreground">
            <div className="flex max-w-sm flex-col items-center text-center space-y-4 rounded-2xl border border-border/60 bg-card/60 p-8 shadow-2xl backdrop-blur-xl">
              <Loader2 className="h-8 w-8 animate-spin text-primary" />
              <div className="space-y-1">
                <h3 className="text-base font-semibold">Atualizando aplicação...</h3>
                <p className="text-xs text-muted-foreground">
                  Recarregando automaticamente para restaurar a tela.
                </p>
              </div>
            </div>
          </div>
        );
      }

      // Caso a falha persista após a tentativa de reload automático
      return (
        <div className="flex h-screen w-full flex-col items-center justify-center bg-background p-6 text-foreground">
          <div className="flex max-w-md flex-col items-center text-center space-y-4 rounded-2xl border border-border/60 bg-card/60 p-8 shadow-2xl backdrop-blur-xl">
            <div className="rounded-full bg-destructive/10 p-4 text-destructive ring-8 ring-destructive/5">
              <AlertTriangle className="h-8 w-8" />
            </div>
            
            <div className="space-y-2">
              <h2 className="text-xl font-bold tracking-tight">Falha persistente</h2>
              <p className="text-sm text-muted-foreground leading-relaxed">
                A tela foi recarregada automaticamente, mas o erro persistiu. Clique abaixo para tentar reiniciar.
              </p>
            </div>

            {this.state.error?.message && (
              <div className="w-full rounded-lg bg-secondary/40 p-3 text-left font-mono text-xs text-muted-foreground overflow-x-auto border border-border/40">
                {this.state.error.message}
              </div>
            )}

            <Button onClick={this.handleManualReset} className="w-full gap-2 mt-2">
              <RefreshCw className="h-4 w-4" />
              Tentar Novamente
            </Button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
