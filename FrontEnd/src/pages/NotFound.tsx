import { useLocation, useNavigate } from "react-router-dom";
import { useEffect } from "react";
import { Button } from "@/components/ui/button";

const NotFound = () => {
  const location = useLocation();
  const navigate = useNavigate();

  useEffect(() => {
    console.error(
      "404 Error: O usuário tentou acessar uma rota inexistente:",
      location.pathname
    );
  }, [location.pathname]);
  const handleBackToDashboard = () => {
    const isAdmin = localStorage.getItem("is_staff") === "true";
    if (isAdmin) {
      navigate("/admin");
    } else {
      navigate("/user");
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-background">
      <div className="text-center space-y-6">
        <h1 className="text-6xl font-bold text-primary">404</h1>
        <p className="text-xl text-muted-foreground">Oops! Página não encontrada</p>
        <Button 
          onClick={handleBackToDashboard}
          className="bg-primary text-primary-foreground px-8 py-6 rounded-xl hover:opacity-90 transition-all"
        >
          Voltar para a Dashboard
        </Button>
      </div>
    </div>
  );
};

export default NotFound;