import { Users, Circle, Loader2 } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import api from "@/services/api";

interface Colaborador {
  id: string;
  first_name: string;
  username: string; 
  avatar_url?: string;
  status: "ONLINE" | "INATIVO"; 
  is_online: boolean;
}

const statusConfig = {
  ONLINE: {
    label: "Online",
    color: "text-green-500",
    fill: "fill-green-500"
  },
  INATIVO: {
    label: "Ausente",
    color: "text-yellow-500",
    fill: "fill-yellow-500"
  },
  OFFLINE: {
    label: "Offline",
    color: "text-muted-foreground",
    fill: "fill-muted-foreground"
  }
};

export function ColaboradoresOnlineCard() {
  const { data: colaboradores = [], isLoading, isError } = useQuery<Colaborador[]>({
    queryKey: ["usuarios-online"], 
    queryFn: async () => {
      const response = await api.get("/users/usuarios/online/"); 
      return response.data?.results || response.data || [];
    },
    refetchInterval: 30000,
    refetchOnWindowFocus: false,
  });
  
  const onlineCount = colaboradores.filter(c => c.status === 'ONLINE').length;

  if (isLoading) {
    return (
      <div className="glass rounded-2xl p-6 h-full flex items-center justify-center">
        <Loader2 className="w-6 h-6 animate-spin text-primary" />
      </div>
    );
  }

  if (isError) {
    return (
      <div className="glass rounded-2xl p-6 h-full flex items-center justify-center text-sm text-muted-foreground">
        Erro ao carregar equipe.
      </div>
    );
  }

  return (
    <div className="glass rounded-2xl p-6 card-hover h-full flex flex-col relative overflow-hidden group border border-border/50">
      <div className="absolute inset-0 bg-gradient-to-br from-primary/5 via-transparent to-accent/5 opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
      
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Equipe</h3>
        <div className="flex items-center gap-1.5">
          <Circle className="w-2 h-2 fill-green-500 text-green-500 animate-pulse" />
          <span className="text-xs text-muted-foreground">{onlineCount} online</span>
        </div>
      </div>
      
      <div className="flex-1 flex flex-col gap-3 relative z-10">
        <div className="flex items-center gap-2 mb-2">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-primary to-accent flex items-center justify-center shadow-lg shadow-primary/25">
            <Users className="w-5 h-5 text-primary-foreground" />
          </div>
          <div>
            <p className="text-sm font-medium text-foreground">Colaboradores</p>
            <p className="text-xs text-muted-foreground">
              {colaboradores.length} recentes
            </p>
          </div>
        </div>

        <div className="flex-1 space-y-2 overflow-auto custom-scrollbar pr-1 max-h-[200px]">
          {colaboradores.length === 0 ? (
             <div className="text-center py-4 text-xs text-muted-foreground">
               Ninguém online nos últimos minutos.
             </div>
          ) : (
            colaboradores.map((colaborador) => {
              const config = statusConfig[colaborador.status] || statusConfig.OFFLINE;

              return (
                <div 
                  key={colaborador.id}
                  className="flex items-center gap-3 p-2 rounded-lg bg-background/50 hover:bg-background/80 transition-colors border border-transparent hover:border-border/20"
                >
                  <div className="w-8 h-8 rounded-full bg-gradient-to-br from-muted to-muted-foreground/20 flex items-center justify-center text-xs font-medium text-foreground border border-border/50 shadow-sm overflow-hidden">
                    {colaborador.avatar_url ? (
                      <img src={colaborador.avatar_url} alt={colaborador.username} className="w-full h-full object-cover" />
                    ) : (
                      (colaborador.first_name || colaborador.username).slice(0, 2).toUpperCase()
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-foreground truncate">
                      {colaborador.first_name || colaborador.username}
                    </p>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <Circle 
                      className={`w-2 h-2 ${config.fill} ${config.color}`} 
                    />
                    <span className={`text-[10px] font-medium ${config.color}`}>
                      {config.label}
                    </span>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}