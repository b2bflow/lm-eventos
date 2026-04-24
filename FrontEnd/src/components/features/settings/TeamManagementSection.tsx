import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Users, Plus, UserMinus, UserPlus, Loader2, Info } from "lucide-react";
import { toast } from "sonner";
import api from "@/services/api";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";

interface Team {
  id: string;
  name: string;
  description: string;
  members: string[];
}

interface User {
  id: number;
  name: string;
  email: string;
}

export function TeamManagementSection() {
  const queryClient = useQueryClient();
  const [selectedTeamId, setSelectedTeamId] = useState<string | null>(null);
  const [newTeamName, setNewTeamName] = useState("");
  const [userToAdd, setUserToAdd] = useState<string>("");

  // 1. Busca Equipas
  const { data: teams = [], isLoading: isLoadingTeams } = useQuery<Team[]>({
    queryKey: ["teams-list"],
    queryFn: async () => {
      const response = await api.get("/users/teams/");
      return response.data;
    }
  });

  // 2. Busca Usuários para mapear os nomes
  const { data: users = [], isLoading: isLoadingUsers } = useQuery<User[]>({
    queryKey: ["team-users"],
    queryFn: async () => {
      const response = await api.get("/users/usuarios/");
      return response.data;
    }
  });

  const createTeamMutation = useMutation({
    mutationFn: async () => {
      await api.post("/users/teams/", { name: newTeamName, description: "Equipe OmniFlow" });
    },
    onSuccess: () => {
      toast.success("Equipa criada com sucesso.");
      setNewTeamName("");
      queryClient.invalidateQueries({ queryKey: ["teams-list"] });
    },
    onError: (error: any) => toast.error(error.response?.data?.detail || "Erro ao criar equipa.")
  });

  const manageMemberMutation = useMutation({
    mutationFn: async ({ action, userId }: { action: 'ADD' | 'REMOVE', userId: string }) => {
      if (!selectedTeamId) return;
      await api.patch(`/users/teams/${selectedTeamId}/members/`, { action, user_id: userId });
    },
    onSuccess: (_, vars) => {
      toast.success(vars.action === 'ADD' ? "Membro adicionado." : "Membro removido.");
      setUserToAdd("");
      queryClient.invalidateQueries({ queryKey: ["teams-list"] });
    },
    onError: (error: any) => toast.error(error.response?.data?.detail || "Erro ao gerir membro.")
  });

  if (isLoadingTeams || isLoadingUsers) {
    return <div className="p-8 flex justify-center"><Loader2 className="animate-spin text-primary w-6 h-6" /></div>;
  }

  const selectedTeam = teams.find(t => t.id === selectedTeamId);
  const usersNotInTeam = users.filter(u => !selectedTeam?.members.includes(u.id.toString()));

  return (
    <div className="flex flex-col md:flex-row gap-6 h-[500px]">
      
      {/* PAINEL ESQUERDO: MASTER (Lista de Equipas) */}
      <div className="w-full md:w-1/3 flex flex-col gap-4 border-r border-border/50 pr-4">
        <div className="flex items-center gap-2 mb-2">
          <Input 
            placeholder="Nome do novo Time..." 
            value={newTeamName}
            onChange={(e) => setNewTeamName(e.target.value)}
            className="bg-secondary/30"
          />
          <Button 
            size="icon" 
            onClick={() => createTeamMutation.mutate()} 
            disabled={!newTeamName || createTeamMutation.isPending}
            className="shrink-0 gradient-primary text-white"
          >
            {createTeamMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
          </Button>
        </div>

        <ScrollArea className="flex-1 pr-2">
          <div className="space-y-2">
            {teams.length === 0 && <p className="text-xs text-muted-foreground text-center mt-4">Nenhuma equipa criada.</p>}
            {teams.map(team => (
              <button
                key={team.id}
                onClick={() => setSelectedTeamId(team.id)}
                className={`w-full flex items-center justify-between p-3 rounded-xl border transition-all text-left ${
                  selectedTeamId === team.id 
                    ? "bg-primary/10 border-primary/30" 
                    : "bg-background/40 border-border/50 hover:bg-secondary/40"
                }`}
              >
                <div>
                  <p className="font-semibold text-sm text-foreground">{team.name}</p>
                  <p className="text-xs text-muted-foreground">{team.members.length} membros</p>
                </div>
              </button>
            ))}
          </div>
        </ScrollArea>
      </div>

      {/* PAINEL DIREITO: DETAIL (Gerir Equipa Selecionada) */}
      <div className="w-full md:w-2/3 flex flex-col">
        {!selectedTeam ? (
          <div className="flex-1 flex flex-col items-center justify-center text-muted-foreground bg-background/20 rounded-2xl border border-dashed border-border/50">
            <Users className="w-12 h-12 mb-4 opacity-20" />
            <p className="text-sm">Selecione um time à esquerda para gerir os seus membros.</p>
          </div>
        ) : (
          <div className="flex-1 flex flex-col animate-in fade-in zoom-in-95 duration-200">
            <div className="mb-6">
              <h3 className="text-xl font-bold text-foreground">{selectedTeam.name}</h3>
              <p className="text-sm text-muted-foreground">Gestão de acessos a esta time.</p>
            </div>

            {/* Adicionar Membro */}
            <div className="flex items-end gap-3 mb-6 p-4 rounded-xl bg-secondary/20 border border-border/50">
              <div className="flex-1 space-y-2">
                <Label>Adicionar Colaborador</Label>
                <Select value={userToAdd} onValueChange={setUserToAdd}>
                  <SelectTrigger className="bg-background">
                    <SelectValue placeholder="Selecione um utilizador..." />
                  </SelectTrigger>
                  <SelectContent>
                    {usersNotInTeam.map(u => (
                      <SelectItem key={u.id} value={u.id.toString()}>{u.name} ({u.email})</SelectItem>
                    ))}
                    {usersNotInTeam.length === 0 && <SelectItem value="none" disabled>Todos os utilizadores já estão nesta equipa.</SelectItem>}
                  </SelectContent>
                </Select>
              </div>
              <Button 
                onClick={() => manageMemberMutation.mutate({ action: 'ADD', userId: userToAdd })}
                disabled={!userToAdd || manageMemberMutation.isPending}
                className="bg-green-600 hover:bg-green-700 text-white"
              >
                <UserPlus className="w-4 h-4 mr-2" /> Adicionar
              </Button>
            </div>

            {/* Lista de Membros Atuais */}
            <Label className="mb-3 block text-muted-foreground">Membros do Time ({selectedTeam.members.length})</Label>
            <ScrollArea className="flex-1 border border-border/50 rounded-xl bg-background/30 p-1">
              {selectedTeam.members.length === 0 ? (
                <div className="flex flex-col items-center justify-center p-8 text-muted-foreground/50">
                  <Info className="w-8 h-8 mb-2" />
                  <span className="text-xs">Esta equipe não tem membros.</span>
                </div>
              ) : (
                <div className="space-y-1">
                  {selectedTeam.members.map(memberId => {
                    const userObj = users.find(u => u.id.toString() === memberId);
                    if (!userObj) return null; 
                    
                    return (
                      <div key={memberId} className="flex items-center justify-between p-3 rounded-lg hover:bg-secondary/30 transition-colors group">
                        <div className="flex items-center gap-3">
                          <Avatar className="h-8 w-8 border border-border">
                            <AvatarFallback className="bg-primary/10 text-primary font-semibold text-xs">
                              {userObj.name.slice(0, 2).toUpperCase()}
                            </AvatarFallback>
                          </Avatar>
                          <div>
                            <p className="text-sm font-medium text-foreground">{userObj.name}</p>
                            <p className="text-xs text-muted-foreground">{userObj.email}</p>
                          </div>
                        </div>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => manageMemberMutation.mutate({ action: 'REMOVE', userId: memberId })}
                          disabled={manageMemberMutation.isPending}
                          className="opacity-0 group-hover:opacity-100 text-red-500 hover:text-red-600 hover:bg-red-500/10 transition-all"
                        >
                          <UserMinus className="w-4 h-4 mr-1" /> Remover
                        </Button>
                      </div>
                    );
                  })}
                </div>
              )}
            </ScrollArea>
          </div>
        )}
      </div>

    </div>
  );
}