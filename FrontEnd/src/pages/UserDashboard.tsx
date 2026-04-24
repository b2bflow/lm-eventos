import { Sidebar } from "@/components/layout/Sidebar";
import { DateFilterProvider } from "@/contexts/DateFilterContext";
import { DashboardGrid } from "@/components/domain/dashboard/DashboardGrid";
import { WelcomeCard } from "@/components/domain/dashboard/WelcomeCard";

const UserDashboard = () => {
  const username = localStorage.getItem("username") || "Operador";

  return (
    <DateFilterProvider>
      <div className="flex h-screen w-full bg-background overflow-hidden">
        <Sidebar />
        <div className="flex-1 flex flex-col min-w-0 h-full overflow-hidden">
          <main className="flex-1 p-6 overflow-y-auto">
            <div className="max-w-7xl mx-auto space-y-6">
              <WelcomeCard userName={username} />
              <DashboardGrid role="user" />
            </div>
          </main>
        </div>
      </div>
    </DateFilterProvider>
  );
};

export default UserDashboard;