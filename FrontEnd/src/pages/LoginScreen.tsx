import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Loader2 } from 'lucide-react';
import api from '@/services/api';

const Login = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setIsLoading(true);

    try {
      const response = await api.post('/users/token/', {
        email,
        password
      });

      const data = response.data;
      
      localStorage.setItem('accessToken', data.access);
      localStorage.setItem('refreshToken', data.refresh);
      localStorage.setItem('is_staff', data.is_admin ? "true" : "false"); 
      localStorage.setItem('username', data.username); 

      const setCookie = (name: string, value: string, maxAgeSec: number) => {
        document.cookie = `${name}=${value}; Path=/; SameSite=Lax; Max-Age=${maxAgeSec};${window.location.protocol === 'https:' ? ' Secure;' : ''}`;
      };
      setCookie('accessToken', data.access, 30 * 60);
      setCookie('refreshToken', data.refresh, 24 * 60 * 60);

      if (data.is_admin) {
        navigate('/admin');
      } else {
        navigate('/user');
      }
      
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Credenciais inválidas ou erro de conexão.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex h-screen w-full bg-background overflow-hidden">
      
      <div className="flex-1 flex flex-col min-w-0 h-full overflow-hidden">        
        <main className="flex-1 p-6 overflow-y-auto flex items-center justify-center">
          <div className="w-full max-w-md flex flex-col items-center gap-8">
            <div className="w-full flex justify-center px-4">
              <img 
                src="/assets/b2b.png" 
                alt="Logo b2bomni" 
                className="w-full max-w-[280px] h-auto object-contain dark:invert" 
              />
            </div>
            <div className="w-full bg-card text-card-foreground border border-border/50 shadow-sm rounded-2xl p-8">
              <form onSubmit={handleSubmit} className="flex flex-col gap-5">
                <div className="text-center text-sm min-h-[20px]">
                  {error && <span className="text-destructive font-medium">{error}</span>}
                </div>

                <div className="flex flex-col gap-2 w-full">
                    <label htmlFor="email" className="text-sm font-medium text-foreground">
                      E-mail
                    </label>
                    <input 
                      type="email" 
                      id="email" 
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      required
                      disabled={isLoading}
                      className="w-full p-3 rounded-lg border border-input bg-background text-foreground text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
                    />
                </div>

                <div className="flex flex-col gap-2 w-full">
                  <label htmlFor="password" className="text-sm font-medium text-foreground">
                    Senha
                  </label>
                  <input 
                    type="password" 
                    id="password" 
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                    disabled={isLoading}
                    className="w-full p-3 rounded-lg border border-input bg-background text-foreground text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
                  />
                </div>

                <button 
                  type="submit" 
                  disabled={isLoading}
                  className="mt-2 bg-primary text-primary-foreground hover:bg-primary/90 p-3 rounded-lg text-sm font-medium cursor-pointer transition-colors disabled:opacity-70 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                >
                  {isLoading ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      Conectando...
                    </>
                  ) : (
                    'Entrar'
                  )}
                </button>
              </form>
            </div>

          </div>
        </main>

        <footer className="border-t border-border/50 bg-secondary/20 py-4 px-6 md:px-10 flex flex-col md:flex-row justify-between items-center gap-4">
          <img 
            src="/assets/b2bfooter.png" 
            alt="b2bflow" 
            className="h-8 w-auto block dark:invert opacity-80" 
          />
          <div className="flex items-center gap-6">
            <a href="#" className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors">Sobre</a>
            <a href="#" className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors">Documentação</a>
            <a href="#" className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors">Suporte</a>
          </div>
        </footer>

      </div>
    </div>
  );
};

export default Login;