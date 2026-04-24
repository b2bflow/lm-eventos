import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage, FormDescription } from "@/components/ui/form";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"; 
import { UserPlus, Eye, EyeOff, User, Mail, AtSign, Lock, ShieldCheck, Loader2 } from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import { useQueryClient } from "@tanstack/react-query"; 
import api from "@/services/api";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";

interface CreateUserProps {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
}

const createUserSchema = z.object({
  nome: z.string().min(2, "Nome deve ter pelo menos 2 caracteres").max(100, "Nome muito longo"),
  email: z.string().email("Email inválido"),
  documento: z.string().optional(),
  username: z.string().min(3, "Username deve ter pelo menos 3 caracteres").max(30, "Username muito longo")
    .regex(/^[a-zA-Z0-9_]+$/, "Username deve conter apenas letras, números e underscore"),
  senha: z.string().min(6, "Senha deve ter pelo menos 6 caracteres"),
  confirmacaoSenha: z.string(),
  is_staff: z.boolean().default(false), 
}).refine((data) => data.senha === data.confirmacaoSenha, {
  message: "As senhas não coincidem",
  path: ["confirmacaoSenha"],
});

type CreateUserForm = z.infer<typeof createUserSchema>;

export default function CriarUsuario({ isOpen, onOpenChange }: CreateUserProps) {
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const { toast } = useToast();
  const queryClient = useQueryClient();

  const form = useForm<CreateUserForm>({
    resolver: zodResolver(createUserSchema),
    defaultValues: {
      nome: "",
      email: "",
      documento: "",
      username: "",
      senha: "",
      confirmacaoSenha: "",
      is_staff: false, 
    },
  });

  const onSubmit = async (data: CreateUserForm) => {
    try {
      await api.post("/users/usuarios/", { 
        username: data.username,
        email: data.email,
        password: data.senha,
        first_name: data.nome,
        is_staff: data.is_staff
      });

      toast({
        title: "Sucesso!",
        description: `O usuário ${data.nome} foi cadastrado como ${data.is_staff ? 'Administrador' : 'Operador'}.`,
      });

      form.reset();
            
      queryClient.invalidateQueries({ queryKey: ["team-users"] });
      
      onOpenChange(false);
    } catch (error: any) {
      const serverMessage = error.response?.data?.email?.[0] || 
                            error.response?.data?.username?.[0] || 
                            "Erro ao criar usuário no banco de dados.";
      
      toast({
        variant: "destructive",
        title: "Erro no cadastro",
        description: serverMessage,
      });
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={(open) => {
      if (!open) form.reset(); // Limpa o form se o usuário fechar clicando fora
      onOpenChange(open);
    }}>
      <DialogContent className="sm:max-w-[550px] glass border-border/50 max-h-[90vh] overflow-y-auto">
        
        <DialogTitle className="flex items-center gap-3 text-2xl font-bold text-foreground">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-primary to-accent flex items-center justify-center shadow-lg shadow-primary/20">
              <UserPlus className="w-5 h-5 text-primary-foreground" />
            </div>
            Criar Novo Usuário
          </DialogTitle>
          <DialogDescription>Cadastre novos colaboradores no sistema.</DialogDescription>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-5">
            
            <FormField
              control={form.control}
              name="nome"
              render={({ field }) => (
                <FormItem>
                  <FormLabel className="flex items-center gap-2">
                    <User className="w-4 h-4" /> Nome Completo
                  </FormLabel>
                  <FormControl>
                    <Input placeholder="Digite o nome completo" className="bg-muted/30 border-border/50" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <FormField
                control={form.control}
                name="email"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel className="flex items-center gap-2">
                      <Mail className="w-4 h-4" /> Email
                    </FormLabel>
                    <FormControl>
                      <Input type="email" placeholder="email@exemplo.com" className="bg-muted/30 border-border/50" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="username"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel className="flex items-center gap-2">
                      <AtSign className="w-4 h-4" /> Username
                    </FormLabel>
                    <FormControl>
                      <Input placeholder="nome_usuario" className="bg-muted/30 border-border/50" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            <FormField
              control={form.control}
              name="is_staff"
              render={({ field }) => (
                <FormItem>
                  <FormLabel className="flex items-center gap-2">
                    <ShieldCheck className="w-4 h-4" /> Nível de Acesso
                  </FormLabel>
                  <Select 
                    onValueChange={(value) => field.onChange(value === "true")} 
                    value={field.value ? "true" : "false"}
                  >
                    <FormControl>
                      <SelectTrigger className="bg-muted/30 border-border/50">
                        <SelectValue placeholder="Selecione o nível" />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      <SelectItem value="false">Operador (Dashboard Limitada)</SelectItem>
                      <SelectItem value="true">Administrador (Acesso Total)</SelectItem>
                    </SelectContent>
                  </Select>
                  <FormMessage />
                </FormItem>
              )}
            />

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <FormField
                control={form.control}
                name="senha"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel className="flex items-center gap-2">
                      <Lock className="w-4 h-4" /> Senha
                    </FormLabel>
                    <FormControl>
                      <div className="relative">
                        <Input type={showPassword ? "text" : "password"} placeholder="******" className="bg-muted/30 border-border/50 pr-10" {...field} />
                        <button type="button" onClick={() => setShowPassword(!showPassword)} className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground">
                          {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                        </button>
                      </div>
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="confirmacaoSenha"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel className="flex items-center gap-2">
                      <Lock className="w-4 h-4" /> Confirmar Senha
                    </FormLabel>
                    <FormControl>
                      <div className="relative">
                        <Input type={showConfirmPassword ? "text" : "password"} placeholder="******" className="bg-muted/30 border-border/50 pr-10" {...field} />
                        <button type="button" onClick={() => setShowConfirmPassword(!showConfirmPassword)} className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground">
                          {showConfirmPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                        </button>
                      </div>
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            <Button 
              type="submit" 
              className="w-full bg-gradient-to-r from-primary to-accent hover:opacity-90 py-6 mt-2"
              disabled={form.formState.isSubmitting}
            >
              {form.formState.isSubmitting ? <><Loader2 className="w-5 h-5 mr-2 animate-spin" /> Cadastrando...</> : "Cadastrar Usuário"}
            </Button>
          </form>
        </Form>
      </DialogContent>                                                   
    </Dialog>
  );
}