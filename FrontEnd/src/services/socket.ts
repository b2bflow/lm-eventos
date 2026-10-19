import { io } from "socket.io-client";

// O Socket.IO roda no backend (mesma URL da API). BASE_URL do Vite é o caminho do próprio painel
// ("/"), o que fazia o socket tentar conectar no domínio do front.
const SOCKET_URL = import.meta.env.VITE_API_URL || window.location.origin;

export const socket = io(SOCKET_URL, {
  autoConnect: false, 
  transports: ["websocket"], 
  // O servidor recusa conexão sem o JWT (as mensagens do WhatsApp só vão para quem está logado).
  // Função: a cada reconexão manda o token atual.
  auth: (cb) => cb({ token: localStorage.getItem("accessToken") || "" }),
  reconnectionAttempts: 5,
});