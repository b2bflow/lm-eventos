import type { ReactNode } from "react";
import { Sidebar } from "@/components/layout/Sidebar";
import { cn } from "@/lib/utils";

interface PageShellProps {
  title: string;
  // Ao lado do título (ex.: abas "Ativos | Arquivados" do funil).
  titleAside?: ReactNode;
  // Botões do cabeçalho (ex.: "Novo chamado"); no celular ficam à direita do título, sem quebrar a linha.
  actions?: ReactNode;
  children: ReactNode;
  // Largura máxima do conteúdo (padrão: 1600px).
  maxWidthClassName?: string;
  // O conteúdo ocupa a altura toda da tela (o último bloco com flex-1 estica até o fim, ex.: quadro do funil).
  fill?: boolean;
}

// Layout padrão de uma tela autenticada: menu, cabeçalho com título e ações, e o conteúdo com rolagem própria.
// Já vem pronto para o celular (barra do menu no topo, espaçamentos menores, título que trunca).
export function PageShell({ title, titleAside, actions, children, maxWidthClassName = "max-w-[1600px]", fill }: PageShellProps) {
  return (
    <div className="flex h-screen w-full bg-background overflow-hidden">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0 h-full overflow-hidden">
        <header className="h-16 sm:h-20 px-4 sm:px-8 border-b border-border/50 flex items-center justify-between gap-3 bg-background/80 backdrop-blur-xl flex-shrink-0">
          <div className="flex min-w-0 items-center gap-3 sm:gap-4">
            <h1 className="min-w-0 truncate text-lg sm:text-xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-primary to-green-600">{title}</h1>
            {titleAside}
          </div>
          {actions && <div className="flex items-center gap-2 flex-shrink-0">{actions}</div>}
        </header>
        <main className={cn("flex-1 p-4 sm:p-6 overflow-y-auto overflow-x-hidden", fill && "flex flex-col")}>
          <div className={cn("mx-auto space-y-4", maxWidthClassName, fill && "flex-1 w-full flex flex-col")}>{children}</div>
        </main>
      </div>
    </div>
  );
}
