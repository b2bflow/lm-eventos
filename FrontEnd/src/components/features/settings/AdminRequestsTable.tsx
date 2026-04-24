import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { CheckCircle, XCircle, Loader2 } from "lucide-react";
import { toast } from "sonner";
import api from "@/services/api";

interface NameRequest {
  id: number;
  current_name: string;
  new_name: string;
  user_email: string;
  created_at: string;
}

export function AdminRequestsTable() {
  const queryClient = useQueryClient();

  const { data: requests = [], isLoading } = useQuery<NameRequest[]>({
    queryKey: ["admin-name-requests"],
    queryFn: async () => {
      const response = await api.get("/users/name_requests/");
      return response.data;
    }
  });

  const processMutation = useMutation({
    mutationFn: async ({ id, action }: { id: number, action: 'APPROVE' | 'REJECT' }) => {
      await api.patch(`/users/name_requests/${id}/`, { action });
    },
    onSuccess: (_, vars) => {
      toast.success(vars.action === 'APPROVE' ? "Solicitação aprovada." : "Solicitação rejeitada.");
      queryClient.invalidateQueries({ queryKey: ["admin-name-requests"] });
      queryClient.invalidateQueries({ queryKey: ["team-users"] }); // Atualiza nomes na tabela principal
    },
    onError: (error: any) => toast.error(error.response?.data?.detail || "Erro ao processar a solicitação.")
  });

  if (isLoading) return <div className="p-8 flex justify-center"><Loader2 className="animate-spin w-6 h-6 text-primary" /></div>;

  if (requests.length === 0) {
    return <div className="p-8 text-center text-muted-foreground text-sm border border-border/50 rounded-xl bg-background/40 glass">Nenhuma solicitação de alteração pendente.</div>;
  }

  return (
    <div className="glass rounded-2xl overflow-hidden border border-border/50 mt-4 animate-in fade-in">
      <Table>
        <TableHeader className="bg-secondary/30">
          <TableRow>
            <TableHead>Usuário</TableHead>
            <TableHead>Nome Atual</TableHead>
            <TableHead>Novo Nome Solicitado</TableHead>
            <TableHead className="text-right">Ações</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {requests.map(req => (
            <TableRow key={req.id}>
              <TableCell className="font-medium">{req.user_email}</TableCell>
              <TableCell className="text-muted-foreground line-through opacity-70">{req.current_name}</TableCell>
              <TableCell className="text-primary font-bold">{req.new_name}</TableCell>
              <TableCell className="text-right space-x-2 whitespace-nowrap">
                <Button 
                  size="sm" variant="outline" 
                  className="text-red-500 border-red-500/20 hover:bg-red-500/10"
                  onClick={() => processMutation.mutate({ id: req.id, action: 'REJECT' })}
                  disabled={processMutation.isPending}
                >
                  <XCircle className="w-4 h-4 mr-1" /> Recusar
                </Button>
                <Button 
                  size="sm" 
                  className="bg-green-600 hover:bg-green-700 text-white"
                  onClick={() => processMutation.mutate({ id: req.id, action: 'APPROVE' })}
                  disabled={processMutation.isPending}
                >
                  <CheckCircle className="w-4 h-4 mr-1" /> Aprovar
                </Button>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}