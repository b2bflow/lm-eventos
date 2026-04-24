import { socket } from "@/services/socket";
import { useQueryClient } from "@tanstack/react-query";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { 
  LayoutDashboard, MessageSquare, Users, Settings, LogOut,
  ChevronLeft, ChevronRight, Circle, Sun, Moon
} from "lucide-react";
import { cn } from "@/lib/utils";
import { normalizeChatMessageContent } from "@/lib/chatMessage";
import { useState, useEffect } from "react";
import { useQuery } from "@tanstack/react-query"; 
import api from "@/services/api"; 
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { ScrollArea } from "@/components/ui/scroll-area";
import { toast } from "sonner";


const MENU_ITEMS = [
  { path: "/admin", icon: LayoutDashboard, label: "Dashboard", adminOnly: true },
  { path: "/user", icon: LayoutDashboard, label: "Dashboard", adminOnly: false },
  { path: "/whatsapp", icon: MessageSquare, label: "WhatsApp", adminOnly: false },
  { path: "/leads", icon: Users, label: "CRM Customer", adminOnly: false },
  //{ path: "/conversoes", icon: BadgeDollarSign, label: "Vendas", adminOnly: false },
  //{ path: "/cancelamentos", icon: XCircle, label: "Cancelamentos", adminOnly: false },
  //{ path: "/usuarios", icon: UserPlus, label: "Usuários", adminOnly: true },
  { path: "/configuracoes", icon: Settings, label: "Configurações", adminOnly: false },
];

export const Sidebar = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const [collapsed, setCollapsed] = useState(false);
  const [isLoggingOut, setIsLoggingOut] = useState(false);
  const queryClient = useQueryClient();

  const [isDark, setIsDark] = useState(() => {
    const savedTheme = localStorage.getItem("theme");
    if (savedTheme) return savedTheme === "dark";
    return document.documentElement.classList.contains("dark");
  });

  useEffect(() => {
    if (isDark) {
      document.documentElement.classList.add('dark');
      localStorage.setItem("theme", "dark");
    } else {
      document.documentElement.classList.remove('dark');
      localStorage.setItem("theme", "light");
    }
  }, [isDark]);

  const toggleTheme = () => setIsDark(!isDark);

  const { data: userProfile } = useQuery({
    queryKey: ["user-profile"],
    queryFn: async () => {
      const response = await api.get("/users/me/"); 
      return response.data;
    },
    retry: false,
  });
  
  const isAdmin = userProfile?.is_staff ?? (localStorage.getItem("is_staff") === "true");
  const username = userProfile?.username || localStorage.getItem("username");

  const { data: onlineUsers } = useQuery({
    queryKey: ["sidebar-online-users"],
    queryFn: async () => {
      const response = await api.get("/users/usuarios/online/");
      return response.data;
    },
    enabled: isAdmin && !collapsed, 
    refetchInterval: 30000, 
  });

  const handleLogout = async () => {
    if (isLoggingOut) return;
    setIsLoggingOut(true);
    try {
      await api.post("/users/logout/"); 
    } catch (error) {
      console.error("Erro no logout:", error);
    } finally {
      localStorage.clear();
      toast.success("Sessão encerrada");
      navigate("/login");
      setIsLoggingOut(false);
    }
  };

  const filteredMenu = MENU_ITEMS.filter(item => {
    if (item.path === "/admin" && !isAdmin) return false;
    if (item.path === "/user" && isAdmin) return false;
    if (item.adminOnly && !isAdmin) return false;
    return true;
  });

  useEffect(() => {
    function onNewMessage(eventData: any) {
      queryClient.setQueryData(["conversations"], (oldConversations: any) => {
        if (!oldConversations) return undefined;
        
        const conversationId = eventData.conversation_id;
        const exists = oldConversations.find((c: any) => c.id === conversationId);
        
        if (exists) {
          const updatedConversation = {
            ...exists,
            last_message_content: normalizeChatMessageContent(eventData.content),
            last_interaction_at: eventData.created_at, 
            unread_count: (exists.unread_count || 0) + (eventData.direction === 'INCOMING' ? 1 : 0)
          };
          const others = oldConversations.filter((c: any) => c.id !== conversationId);
          return [updatedConversation, ...others];
        } else {
          queryClient.invalidateQueries({ queryKey: ["conversations"] });
          return oldConversations;
        }
      });
      
      if (location.pathname !== "/whatsapp" && eventData.direction === 'INCOMING') {
        toast.info("Nova mensagem recebida no WhatsApp!");
      }
    }

    if (!socket.connected) socket.connect();
    socket.on("new_message", onNewMessage);
    
    return () => {
      socket.off("new_message", onNewMessage);
    };
  }, [queryClient, location.pathname]);

  return (
    <div className={cn("h-screen bg-card/80 backdrop-blur-xl border-r border-border/50 flex flex-col transition-all duration-300 relative z-50 shadow-xl", collapsed ? "w-20" : "w-72")}>
      <button onClick={() => setCollapsed(!collapsed)} className="absolute -right-3 top-9 bg-background border border-border p-1.5 rounded-full shadow-md hover:bg-muted text-foreground z-50 transition-all hover:scale-110">
        {collapsed ? <ChevronRight className="w-3 h-3" /> : <ChevronLeft className="w-3 h-3" />}
      </button>

      <div className="h-20 flex items-center px-6 border-b border-border/50 bg-background/20">
        <div className="flex items-center gap-3 overflow-hidden">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-primary to-accent flex-shrink-0 flex items-center justify-center shadow-lg shadow-primary/20 ring-1 ring-white/10">
            <span className="text-primary-foreground font-bold text-xl">O</span>
          </div>
          {!collapsed && (
            <div className="flex flex-col animate-in fade-in slide-in-from-left-2 duration-300">
              <span className="font-bold text-xl tracking-tight text-foreground leading-none">Omni<span className="text-primary">Flow</span></span>
              <span className="text-[10px] text-muted-foreground font-medium tracking-widest uppercase">Workspace</span>
            </div>
          )}
        </div>
      </div>

      <ScrollArea className="flex-1 py-4 px-3">
        <nav className="space-y-1.5">
          {filteredMenu.map((item) => {
            const isActive = location.pathname === item.path;
            return (
              <Link key={item.path} to={item.path} className={cn("flex items-center gap-3 px-3 py-2.5 rounded-xl transition-all group relative overflow-hidden", isActive ? "bg-primary/10 text-primary font-medium" : "text-muted-foreground hover:text-foreground hover:bg-muted/50", collapsed ? "justify-center" : "")}>
                {isActive && <div className="absolute left-0 top-0 bottom-0 w-1 bg-primary rounded-r-full" />}
                <item.icon className={cn("w-5 h-5 flex-shrink-0", isActive ? "text-primary" : "group-hover:text-foreground")} />
                {!collapsed && <span>{item.label}</span>}
              </Link>
            );
          })}
        </nav>  
      </ScrollArea>

      <div className="p-4 border-t border-border/50 bg-muted/10 space-y-3">
        {/* BOTÃO DE TEMA CORRIGIDO */}
        <button 
          onClick={toggleTheme} 
          className={cn("flex items-center gap-3 px-3 py-2 w-full rounded-xl transition-all text-muted-foreground hover:text-foreground hover:bg-muted/50", collapsed && "justify-center")} 
          title="Alternar Tema"
        >
          {!isDark ? <Sun className="w-5 h-5 text-yellow-500" /> : <Moon className="w-5 h-5 text-blue-400" />}
          {!collapsed && <span className="text-sm font-medium">Modo {!isDark ? 'Claro' : 'Escuro'}</span>}
        </button>

        <div className={cn("flex items-center gap-3 p-2.5 rounded-xl border border-border/50 bg-background/50 group shadow-sm transition-all", collapsed ? "justify-center p-2" : "")}>
          <Avatar className={cn("border border-border", collapsed ? "h-8 w-8" : "h-10 w-10")}>
            <AvatarFallback className="bg-gradient-to-br from-primary to-accent text-primary-foreground font-bold">{username?.charAt(0).toUpperCase() || "U"}</AvatarFallback>
          </Avatar>
          {!collapsed && (
            <div className="flex-1 min-w-0 flex flex-col">
              <span className="text-sm font-semibold truncate text-foreground group-hover:text-primary transition-colors">{username}</span>
              <span className="text-[10px] text-muted-foreground uppercase font-bold tracking-wider flex items-center gap-1.5"><Circle className="w-1.5 h-1.5 fill-green-500 text-green-500" />{isAdmin ? "Admin" : "Operador"}</span>
            </div>
          )}
          {!collapsed && (
            <button onClick={handleLogout} disabled={isLoggingOut} className="text-muted-foreground hover:text-destructive hover:bg-destructive/10 p-2 rounded-lg transition-all" title="Sair">
              <LogOut className={cn("w-4 h-4", isLoggingOut && "animate-pulse")} />
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
