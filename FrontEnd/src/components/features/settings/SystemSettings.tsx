import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Save, Smartphone, Zap, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api from "@/services/api";

export function SystemSettings() {
  const queryClient = useQueryClient();

  const [formData, setFormData] = useState({
    webhook_token: "",
    zapi_instance_id: "",
    zapi_token: "",
    openai_api_key: "",
    ai_active: true,
  });

  const { data: config, isLoading } = useQuery({
    queryKey: ["system-config"],
    queryFn: async () => {
      const response = await api.get("/chat/configuracoes/");
      return response.data;
    },
  });

  useEffect(() => {
    if (config) {
      setFormData({
        webhook_token: config.webhook_token || "",
        zapi_instance_id: config.zapi_instance_id || "",
        zapi_token: config.zapi_token || "",
        openai_api_key: config.openai_api_key || "",
        ai_active: config.ai_active ?? true,
      });
    }
  }, [config]);

  const saveMutation = useMutation({
    mutationFn: async () => {
      await api.post("/chat/configuracoes/", formData);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["system-config"] });
      toast.success("Configurações globais salvas com sucesso!");
    },
    onError: () => toast.error("Erro ao salvar configurações do sistema."),
  });

  if (isLoading) {
    return <div className="flex justify-center p-8"><Loader2 className="animate-spin text-primary w-6 h-6" /></div>;
  }

  return (
    <div className="space-y-6">
      
      <div className="p-6 rounded-2xl border border-border/50 bg-background/40 backdrop-blur-xl shadow-sm relative overflow-hidden group">
        <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
          <Smartphone className="w-24 h-24" />
        </div>
        
        <div className="mb-6 relative z-10">
          <h3 className="text-lg font-semibold text-foreground flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
            Integração WhatsApp (Z-API)
          </h3>
          <p className="text-sm text-muted-foreground">Credenciais da API e Token de segurança do Webhook.</p>
        </div>

        <div className="grid grid-cols-3 md:grid-cols-3 gap-6 relative z-10">
          <div className="space-y-2">
            <Label>ID da Instância (Z-API)</Label>
            <Input 
              value={formData.zapi_instance_id}
              onChange={(e) => setFormData({ ...formData, zapi_instance_id: e.target.value })}
              placeholder="Ex: 3B45F6A..." 
              className="bg-secondary/30 border-border/50 font-mono text-sm" 
            />
          </div>
          <div className="space-y-2">
            <Label>Token da Instância (Z-API)</Label>
            <Input 
              type="password"
              value={formData.zapi_token}
              onChange={(e) => setFormData({ ...formData, zapi_token: e.target.value })}
              placeholder="••••••••••••••••" 
              className="bg-secondary/30 border-border/50 font-mono text-sm" 
            />
          </div>
          <div className="space-y-2">
            <Label>Token de Segurança (Webhook)</Label>
            <Input 
              type="password"
              value={formData.webhook_token}
              onChange={(e) => setFormData({ ...formData, webhook_token: e.target.value })}
              placeholder="••••••••••••••••" 
              className="bg-secondary/30 border-border/50 font-mono text-sm" 
            />
          </div>
        </div>
      </div>

      <div className="p-6 rounded-2xl border border-border/50 bg-background/40 backdrop-blur-xl shadow-sm">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h3 className="text-lg font-semibold text-foreground flex items-center gap-2">
              <Zap className="w-4 h-4 text-purple-500" />
              Inteligência Artificial (OpenAI)
            </h3>
            <p className="text-sm text-muted-foreground">Chave de API do agente (Prompt gerido internamente).</p>
          </div>
          <div className="flex items-center gap-2 bg-secondary/30 p-2 rounded-lg border border-border/50">
            <Label htmlFor="ai-active" className="text-xs font-bold cursor-pointer">IA Ativa Globalmente</Label>
            <Switch 
              id="ai-active" 
              checked={formData.ai_active}
              onCheckedChange={(checked) => setFormData({ ...formData, ai_active: checked })}
            />
          </div>
        </div>

        <div className="grid grid-cols-1 gap-6">
          <div className="space-y-2">
            <Label>OpenAI API Key</Label>
            <Input 
              type="password" 
              value={formData.openai_api_key}
              onChange={(e) => setFormData({ ...formData, openai_api_key: e.target.value })}
              placeholder="sk-proj-..." 
              className="bg-secondary/30 border-border/50 font-mono text-sm" 
            />
          </div>
        </div>
      </div>

      <div className="flex justify-end">
        <Button 
          onClick={() => saveMutation.mutate()} 
          disabled={saveMutation.isPending}
          className="gradient-primary text-white shadow-lg shadow-primary/20"
        >
          {saveMutation.isPending ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Save className="w-4 h-4 mr-2" />} 
          Guardar Configurações
        </Button>
      </div>
    </div>
  );
}