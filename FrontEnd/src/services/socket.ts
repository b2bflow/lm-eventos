import { io } from "socket.io-client";

const baseUrl = import.meta.env.BASE_URL;

const SOCKET_URL = `${baseUrl}`;

export const socket = io(SOCKET_URL, {
  autoConnect: false, 
  transports: ["websocket"], 
  // O servidor recusa conexão sem o JWT (as mensagens do WhatsApp só vão para quem está logado).
  // Função: a cada reconexão manda o token atual.
  auth: (cb) => cb({ token: localStorage.getItem("accessToken") || "" }),
  reconnectionAttempts: 5,
});