import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Loader2, Send, Clock } from "lucide-react";
import { toast } from "sonner";
import api from "@/services/api";

export function NameChangeSection({ currentName }: { currentName: string }) {
  const [newName, setNewName] = useState("");
  const queryClient = useQueryClient();

  // Verifica se o usuário já tem uma solicitação pendente
  const { data: pendingData, isLoading } = useQuery({
    queryKey: ["pending-name-request"],
    queryFn: async () => {
      const response = await api.get("/users/name_requests/");
      return response.data;
    }
  });

  const requestMutation = useMutation({
    mutationFn: async () => {
      await api.post("/users/name_requests/", { new_name: newName });
    },
    onSuccess: () => {
      toast.success("Solicitação enviada para análise do Administrador.");
      setNewName("");
      queryClient.invalidateQueries({ queryKey: ["pending-name-request"] });
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || "Erro ao solicitar alteração.");
    }
  });

  const hasPending = pendingData?.has_pending;

  if (isLoading) return <div className="h-10 flex items-center"><Loader2 className="w-4 h-4 animate-spin text-primary" /></div>;

  return (
    <div className="space-y-2">
      <Label>Username / Nome de Exibição</Label>
      
      {hasPending ? (
        <div className="bg-yellow-500/10 border border-yellow-500/20 text-yellow-600 rounded-lg p-3 text-sm flex items-center gap-2">
          <Clock className="w-4 h-4 shrink-0" />
          <p>Você possui uma solicitação de alteração em análise. Aguarde a aprovação do Administrador.</p>
        </div>
      ) : (
        <div className="flex gap-2">
          <Input 
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder={`Atual: ${currentName}`} 
            className="bg-secondary/30 border-border/50" 
          />
          <Button 
            onClick={() => requestMutation.mutate()} 
            disabled={!newName || newName === currentName || requestMutation.isPending}
            className="whitespace-nowrap gradient-primary text-white"
          >
            {requestMutation.isPending ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Send className="w-4 h-4 mr-2" />} 
            Solicitar Troca
          </Button>
        </div>
      )}
    </div>
  );
}