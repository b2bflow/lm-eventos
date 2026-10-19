import axios from 'axios';

// Usando o nome correto com o prefixo VITE_
const baseUrl = import.meta.env.VITE_API_URL;
console.log("A URL BASE DA API É:", baseUrl); 

const api = axios.create({
  baseURL: `${baseUrl}/api/v1/`,
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('accessToken');
  if (token && token !== 'undefined' && token !== 'null') {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

const AUTH_KEYS = ['accessToken', 'refreshToken', 'is_staff', 'username'];

function endSession() {
  AUTH_KEYS.forEach((key) => localStorage.removeItem(key));
  window.location.href = '/login';
}

// Uma renovação por vez: as várias chamadas que levam 401 juntas esperam o mesmo refresh.
let refreshing: Promise<string> | null = null;

function refreshAccessToken(): Promise<string> {
  if (!refreshing) {
    const refresh = localStorage.getItem('refreshToken');
    refreshing = (refresh
      ? axios.post(`${baseUrl}/api/v1/users/token/refresh/`, { refresh }).then(({ data }) => {
          localStorage.setItem('accessToken', data.access);
          // O backend gira o refresh (o antigo vai para a lista negra): guardar o novo.
          if (data.refresh) localStorage.setItem('refreshToken', data.refresh);
          return data.access as string;
        })
      : Promise.reject(new Error('sem refresh token'))
    ).finally(() => {
      refreshing = null;
    });
  }
  return refreshing;
}

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const config = error.config;
    if (error.response?.status !== 401 || !config || config.url?.includes('/token/')) {
      return Promise.reject(error);
    }
    if (config._retried) {
      endSession();
      return Promise.reject(error);
    }
    try {
      const access = await refreshAccessToken();
      config._retried = true;
      config.headers.Authorization = `Bearer ${access}`;
      return api(config);
    } catch {
      endSession();
      return Promise.reject(error);
    }
  }
);

/** Erro do axios com o corpo padrão da API ({detail} ou erros por campo). */
export interface ApiError {
  response?: { status?: number; data?: { detail?: string } & Record<string, unknown> };
}

export default api;