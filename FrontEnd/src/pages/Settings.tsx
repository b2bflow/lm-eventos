import { useState, useEffect } from "react";
import { Sidebar } from "@/components/layout/Sidebar";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { User, Settings as SettingsIcon, Users, Lock, Key } from "lucide-react";
import { ProfileSettings } from "@/components/features/settings/ProfileSettings";
import { SystemSettings } from "@/components/features/settings/SystemSettings";
import { TeamSettings } from "@/components/features/settings/TeamSettings";


export default function Settings() {
  const [isAdmin, setIsAdmin] = useState(false);

  useEffect(() => {
    const isStaff = localStorage.getItem("is_staff") === "true";
    setIsAdmin(isStaff);
  }, []);

  return (
    <div className="flex h-screen w-full bg-background overflow-hidden">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0 h-full overflow-hidden bg-background/50">
        
        {/* Header Simples */}
        <header className="h-16 px-8 border-b border-border/50 flex items-center justify-between bg-background/80 backdrop-blur-xl">
          <h1 className="text-xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-primary to-purple-600">
            Configurações do Sistema
          </h1>
        </header>

        {/* Conteúdo com Tabs */}
        <div className="flex-1 overflow-y-auto p-8">
          <div className="max-w-5xl mx-auto">
            <Tabs defaultValue="profile" className="w-full space-y-6">
              
              <TabsList className="bg-secondary/30 border border-border/50 p-1 h-12 rounded-xl backdrop-blur-md">
                <TabsTrigger value="profile" className="rounded-lg data-[state=active]:bg-background data-[state=active]:shadow-sm transition-all gap-2">
                  <User className="w-4 h-4" /> Meu Perfil
                </TabsTrigger>
                
                {isAdmin && (
                  <>
                    <TabsTrigger value="team" className="rounded-lg data-[state=active]:bg-background data-[state=active]:shadow-sm transition-all gap-2">
                      <Users className="w-4 h-4" /> Equipe
                    </TabsTrigger>
                    <TabsTrigger value="system" className="rounded-lg data-[state=active]:bg-background data-[state=active]:shadow-sm transition-all gap-2">
                      <Key className="w-4 h-4" /> Integrações & API
                    </TabsTrigger>
                  </>
                )}
              </TabsList>

              {/* CONTEÚDO DAS ABAS */}
              
              <TabsContent value="profile" className="animate-in fade-in slide-in-from-bottom-4 duration-500">
                <ProfileSettings />
              </TabsContent>

              {isAdmin && (
                <>
                  <TabsContent value="team" className="animate-in fade-in slide-in-from-bottom-4 duration-500">
                    <TeamSettings />
                  </TabsContent>
                  <TabsContent value="system" className="animate-in fade-in slide-in-from-bottom-4 duration-500">
                    <SystemSettings />
                  </TabsContent>
                </>
              )}

            </Tabs>
          </div>
        </div>
      </div>
    </div>
  );
}