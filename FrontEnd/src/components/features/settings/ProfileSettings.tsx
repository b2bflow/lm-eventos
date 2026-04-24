import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Lock, Mail, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { useQuery, useMutation } from "@tanstack/react-query";
import api from "@/services/api";

// Importação do nosso novo componente modularizado
import { NameChangeSection } from "./NameChangeSection";

export function ProfileSettings() {
  const [passwords, setPasswords] = useState({ old_password: "", new_password: "" });

  const { data: user, isLoading } = useQuery({
    queryKey: ["user-profile"],
    queryFn: async () => {
      const response = await api.get("/users/me/");
      return response.data;
    },
  });

  const updatePasswordMutation = useMutation({
    mutationFn: async () => {
      await api.post("/users/change_password/", passwords);
    },
    onSuccess: () => {
      setPasswords({ old_password: "", new_password: "" });
      toast.success("Sua senha foi alterada com segurança!");
    },
    onError: (error: any) => {
      const msg = error.response?.data?.detail || "Erro ao alterar senha.";
      toast.error(msg);
    },
  });

  if (isLoading) return <div className="flex justify-center p-8"><Loader2 className="animate-spin text-primary w-6 h-6" /></div>;

  return (
    <div className="space-y-6">
      
      {/* SEÇÃO DE INFORMAÇÕES PESSOAIS */}
      <div className="p-6 rounded-2xl border border-border/50 bg-background/40 backdrop-blur-xl shadow-sm">
        <div className="flex items-start justify-between mb-6">
          <div>
            <h3 className="text-lg font-semibold text-foreground">Informações Pessoais</h3>
            <p className="text-sm text-muted-foreground">O seu e-mail de acesso e solicitações de Username.</p>
          </div>
          <Avatar className="w-16 h-16 border-2 border-primary/20">
            <AvatarImage src="" />
            <AvatarFallback className="bg-gradient-to-br from-primary/20 to-purple-500/20 text-xl font-bold text-primary uppercase">
              {user?.first_name?.slice(0, 2) || user?.username?.slice(0, 2) || "U"}
            </AvatarFallback>
          </Avatar>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* O COMPONENTE DE NOME ASSUME O CONTROLE DESTA ÁREA */}
          <NameChangeSection currentName={user?.first_name || ""} />
          
          <div className="space-y-2">
            <Label>E-mail de Acesso (Fixo)</Label>
            <div className="relative">
              <Mail className="absolute left-3 top-3 w-4 h-4 text-muted-foreground" />
              <Input 
                value={user?.email || ""}
                disabled
                className="pl-10 bg-secondary/30 border-border/50 text-muted-foreground opacity-70" 
              />
            </div>
          </div>
        </div>
      </div>

      {/* SEÇÃO DE SEGURANÇA (SENHA) MANTIDA E FUNCIONAL */}
      <div className="p-6 rounded-2xl border border-border/50 bg-background/40 backdrop-blur-xl shadow-sm">
        <div className="mb-6">
          <h3 className="text-lg font-semibold text-foreground flex items-center gap-2">
            <Lock className="w-4 h-4 text-primary" /> Segurança
          </h3>
          <p className="text-sm text-muted-foreground">Alterar sua senha de acesso ao sistema.</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
          <div className="space-y-2">
            <Label>Senha Atual</Label>
            <Input 
              type="password" 
              value={passwords.old_password}
              onChange={(e) => setPasswords({...passwords, old_password: e.target.value})}
              placeholder="•••••••" 
              className="bg-secondary/30 border-border/50" 
            />
          </div>
          <div className="space-y-2">
            <Label>Nova Senha</Label>
            <Input 
              type="password" 
              value={passwords.new_password}
              onChange={(e) => setPasswords({...passwords, new_password: e.target.value})}
              placeholder="•••••••" 
              className="bg-secondary/30 border-border/50" 
            />
          </div>
        </div>

        <div className="flex justify-end">
          <Button 
            onClick={() => updatePasswordMutation.mutate()} 
            disabled={!passwords.old_password || !passwords.new_password || updatePasswordMutation.isPending}
            variant="outline"
            className="border-primary/50 text-primary hover:bg-primary/10"
          >
            {updatePasswordMutation.isPending ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Lock className="w-4 h-4 mr-2" />}
            Atualizar Senha
          </Button>
        </div>
      </div>

    </div>
  );
}