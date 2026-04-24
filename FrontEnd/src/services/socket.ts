import { io } from "socket.io-client";

const baseUrl = import.meta.env.BASE_URL;

const SOCKET_URL = `${baseUrl}`;

export const socket = io(SOCKET_URL, {
  autoConnect: false, 
  transports: ["websocket"], 
  reconnectionAttempts: 5,
});