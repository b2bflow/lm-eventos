import { Sparkles, AlertCircle } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import api from "@/services/api";

interface WelcomeCardProps {
  userName: string;
}

export function WelcomeCard({ userName }: WelcomeCardProps) {
  const hour = new Date().getHours();
  const greeting = hour < 12 ? "Bom dia" : hour < 18 ? "Boa tarde" : "Boa noite";

  // Busca as conversas na API com polling de 5 segundos para manter a dashboard viva
  const { data: conversations = [] } = useQuery({
    queryKey: ['conversations-priority'],
    queryFn: async () => {
      const { data } = await api.get('/chat/conversations/');
      return data.results || [];
    },
    refetchInterval: 5000 
  });

  // Conta quantas conversas estão abertas e com a flag de prioridade ativada pela IA
  const priorityCount = conversations.filter(
    (c: any) => c.needs_attention && c.status !== 'CLOSED'
  ).length;

  return (
    <div className="relative overflow-hidden rounded-xl gradient-primary p-6 glow-accent">
      <div className="absolute top-0 right-0 w-64 h-64 bg-accent/20 rounded-full blur-3xl -translate-y-1/2 translate-x-1/2" />
      <div className="absolute bottom-0 left-0 w-48 h-48 bg-primary-foreground/10 rounded-full blur-2xl translate-y-1/2 -translate-x-1/2" />
      
      <div className="relative z-10">
        <div className="flex items-center gap-2 mb-2">
          <Sparkles className="w-5 h-5 text-accent animate-pulse-slow" />
          <span className="text-sm text-primary-foreground/80">{greeting}</span>
        </div>
        <h1 className="text-2xl font-bold text-primary-foreground mb-1">{userName}</h1>
        
        <p className="text-sm text-primary-foreground/70 flex items-center gap-2 mt-2">
          <AlertCircle className={`w-4 h-4 ${priorityCount > 0 ? "text-amber-400 animate-pulse" : "text-primary-foreground/50"}`} />
          {priorityCount > 0 ? (
            <>
              Você tem <span className="font-semibold text-amber-400">{priorityCount} {priorityCount === 1 ? 'conversa' : 'conversas'}</span> aguardando atendimento prioritário.
            </>
          ) : (
            <>
              Nenhuma conversa aguardando atendimento prioritário no momento.
            </>
          )}
        </p>
      </div>
    </div>
  );
}