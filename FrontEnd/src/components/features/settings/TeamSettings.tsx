import { useState } from "react"; 
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Plus, MoreVertical, Shield, User, Loader2, CheckCircle, XCircle } from "lucide-react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api from "@/services/api";
import { toast } from "sonner";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { AdminRequestsTable } from "./AdminRequestsTable";
import CriarUsuario from "./CreateUser";
import { TeamManagementSection } from "./TeamManagementSection";

interface TeamMember {
  id: number;
  name: string;
  email: string;
  role: "ADMIN" | "OPERATOR";
  status: "ACTIVE" | "INACTIVE";
}

export function TeamSettings() {
  const queryClient = useQueryClient();
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false); // ADICIONADO ESTADO DO MODAL

  const { data: team = [], isLoading } = useQuery<TeamMember[]>({
    queryKey: ["team-users"],
    queryFn: async () => {
      const response = await api.get("/users/usuarios/");
      return response.data;
    },
  });

  const updateAccessMutation = useMutation({
    mutationFn: async ({ id, payload }: { id: number, payload: any }) => {
      await api.patch(`/users/usuarios/${id}/`, payload);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["team-users"] });
      toast.success("Permissões atualizadas com sucesso.");
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || "Erro ao atualizar permissões.");
    }
  });

  const handleToggleRole = (user: TeamMember) => {
    const newIsStaff = user.role !== "ADMIN";
    updateAccessMutation.mutate({ id: user.id, payload: { is_staff: newIsStaff } });
  };

  const handleToggleStatus = (user: TeamMember) => {
    const newIsActive = user.status !== "ACTIVE";
    updateAccessMutation.mutate({ id: user.id, payload: { is_active: newIsActive } });
  };

  if (isLoading) return <div className="flex justify-center p-8"><Loader2 className="animate-spin text-primary w-6 h-6" /></div>;

  return (
    <div className="space-y-6">
      
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold text-foreground">Gestão de Equipe</h3>
          <p className="text-sm text-muted-foreground">Gerencie acessos, funções e solicitações dos colaboradores.</p>
        </div>
        {/* BOTÃO ALTERADO PARA ABRIR O MODAL EM VEZ DE MUDAR DE PÁGINA */}
        <Button onClick={() => setIsCreateModalOpen(true)} className="gradient-primary text-white shadow-md">
          <Plus className="w-4 h-4 mr-2" /> Novo Usuário
        </Button>
      </div>

      <Tabs defaultValue="team" className="w-full">
        <TabsList className="mb-4 bg-secondary/30 border border-border/50">
          <TabsTrigger value="team">Lista de Colaboradores</TabsTrigger>
          <TabsTrigger value="groups">Times</TabsTrigger>
          <TabsTrigger value="requests">Solicitações</TabsTrigger>
        </TabsList>
        
        <TabsContent value="team">
          <div className="glass rounded-2xl overflow-hidden border border-border/50">
            <Table>
              <TableHeader className="bg-secondary/30">
                <TableRow className="hover:bg-transparent border-border/50">
                  <TableHead>Usuário</TableHead>
                  <TableHead>Função</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Ações</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {team.map((user) => (
                  <TableRow key={user.id} className="hover:bg-secondary/20 border-border/50 transition-colors">
                    <TableCell>
                      <div className="flex items-center gap-3">
                        <Avatar className="h-9 w-9 border border-border">
                          <AvatarFallback className="bg-primary/10 text-primary font-semibold">
                            {user.name.slice(0, 2).toUpperCase()}
                          </AvatarFallback>
                        </Avatar>
                        <div>
                          <p className="text-sm font-medium text-foreground">{user.name}</p>
                          <p className="text-xs text-muted-foreground">{user.email}</p>
                        </div>
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        {user.role === "ADMIN" ? (
                          <Badge variant="outline" className="bg-purple-500/10 text-purple-600 border-purple-500/20">
                            <Shield className="w-3 h-3 mr-1" /> Admin
                          </Badge>
                        ) : (
                          <Badge variant="outline" className="bg-blue-500/10 text-blue-600 border-blue-500/20">
                            <User className="w-3 h-3 mr-1" /> Operador
                          </Badge>
                        )}
                      </div>
                    </TableCell>
                    <TableCell>
                      {user.status === "ACTIVE" ? (
                        <span className="text-xs font-medium text-green-600 bg-green-500/10 px-2 py-1 rounded-full border border-green-500/20">Ativo</span>
                      ) : (
                        <span className="text-xs font-medium text-red-600 bg-red-500/10 px-2 py-1 rounded-full border border-red-500/20">Inativo</span>
                      )}
                    </TableCell>
                    <TableCell className="text-right">
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="icon" className="h-8 w-8 hover:bg-primary/10">
                            <MoreVertical className="w-4 h-4 text-muted-foreground hover:text-primary" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem onClick={() => handleToggleRole(user)} disabled={updateAccessMutation.isPending}>
                            <Shield className="w-4 h-4 mr-2" /> 
                            {user.role === "ADMIN" ? "Rebaixar para Operador" : "Promover a Admin"}
                          </DropdownMenuItem>
                          <DropdownMenuItem onClick={() => handleToggleStatus(user)} disabled={updateAccessMutation.isPending}>
                            {user.status === "ACTIVE" ? (
                               <><XCircle className="w-4 h-4 mr-2 text-red-500" /> <span className="text-red-500">Inativar Conta</span></>
                            ) : (
                               <><CheckCircle className="w-4 h-4 mr-2 text-green-500" /> <span className="text-green-500">Ativar Conta</span></>
                            )}
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </TableCell>
                  </TableRow>
                ))}
                
                {team.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={4} className="h-24 text-center text-muted-foreground">
                      Nenhum usuário encontrado na equipe.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </div>
        </TabsContent>

        <TabsContent value="groups">
          <div className="glass rounded-2xl p-6 border border-border/50 animate-in fade-in slide-in-from-bottom-2">
            <TeamManagementSection />
          </div>
        </TabsContent>

        <TabsContent value="requests">
          <AdminRequestsTable />
        </TabsContent>

      </Tabs>
      <CriarUsuario isOpen={isCreateModalOpen} onOpenChange={setIsCreateModalOpen} />
    </div>
  );
}