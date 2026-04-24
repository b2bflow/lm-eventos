import { Sidebar } from "@/components/layout/Sidebar";
import { DateFilterProvider } from "@/contexts/DateFilterContext";
import { DashboardGrid } from "@/components/domain/dashboard/DashboardGrid";
import { WelcomeCard } from "@/components/domain/dashboard/WelcomeCard"; // Pode ser movido para shared futuramente

const Index = () => {
  const username = localStorage.getItem("username") || "Administrador";

  return (
    <DateFilterProvider>
      <div className="flex h-screen w-full bg-background overflow-hidden">
        <Sidebar />
        <div className="flex-1 flex flex-col min-w-0 h-full overflow-hidden">
          <main className="flex-1 p-6 overflow-y-auto">
            <div className="max-w-9xl mx-auto space-y-6">
              {/* corrigir para mostrar somente conversas pendentes */}
              {/*<WelcomeCard userName={username} />*/}
              <DashboardGrid role="admin" />
            </div>
          </main>
        </div>
      </div>
    </DateFilterProvider>
  );
};

export default Index;