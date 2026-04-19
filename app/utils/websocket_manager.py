from fastapi import WebSocket
from typing import List


class ConnectionManager:
    """Gestiona las conexiones WebSocket activas"""
    
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        """Acepta y registra una nueva conexión"""
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"✅ Cliente WebSocket conectado. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        """Elimina una conexión de la lista"""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        print(f"🔌 Cliente WebSocket desconectado. Total: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        """Envía un mensaje a todos los clientes conectados"""
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                print(f"❌ Error enviando a cliente: {e}")
                disconnected.append(connection)
        
        # Limpiar conexiones muertas
        for conn in disconnected:
            self.disconnect(conn)
    