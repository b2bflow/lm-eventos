import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";

import Login from "./pages/LoginScreen";
import Index from "./pages/Index";
import UserDashboard from "./pages/UserDashboard";
import WhatsApp from "./pages/WhatsApp"; 
import Leads from "./pages/Leads"; 
import NotFound from "./pages/NotFound";
import Settings from "@/pages/Settings";

const queryClient = new QueryClient();

const PrivateRoute = ({ children, adminOnly = false }: { children: React.ReactNode; adminOnly?: boolean }) => {
  const token = localStorage.getItem("accessToken");
  const isAdmin = localStorage.getItem("is_staff") === "true";

  if (!token) {
    window.location.href = "/login"; 
    return null;
  }

  if (adminOnly && !isAdmin) {
    return <Navigate to="/user" replace />;
  }

  return <>{children}</>;
};

const isAuthenticated = () => !!localStorage.getItem("accessToken");

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      <Toaster />
      <Sonner />
      <BrowserRouter>
        <Routes>
          <Route path="/" element={isAuthenticated() ? <Navigate to="/admin" /> : <Navigate to="/login" />} />
          <Route path="/login" element={<Login />} />
          <Route path="/admin" element={<PrivateRoute adminOnly><Index /></PrivateRoute>} />
          <Route path="/user" element={<PrivateRoute><UserDashboard /></PrivateRoute>} />
          <Route path="/whatsapp" element={<PrivateRoute><WhatsApp /></PrivateRoute>} />
          <Route path="/leads" element={<PrivateRoute><Leads /></PrivateRoute>} />
          <Route path="/configuracoes" element={<PrivateRoute><Settings /></PrivateRoute>} />
          
          <Route path="*" element={<NotFound />} />
        </Routes>
      </BrowserRouter>
    </TooltipProvider>
  </QueryClientProvider>
);

export default App;