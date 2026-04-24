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

api.interceptors.response.use(
  (response) => response, 
  (error) => {
    if (error.response?.status === 401 && !error.config.url.includes('/token/')) {
      localStorage.removeItem('accessToken');
      localStorage.removeItem('is_staff');
      localStorage.removeItem('username');
      window.location.href = '/login'; 
    }
    return Promise.reject(error);
  }
);

export default api;