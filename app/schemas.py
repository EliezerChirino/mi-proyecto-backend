from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import Optional, List
from datetime import datetime
import re


# ============ DEVICE SCHEMAS ============

class DeviceBase(BaseModel):
    """Schema base de dispositivo"""
    node_id: str = Field(..., min_length=1, max_length=50, description="ID único del nodo (node_1, node_2, etc)")
    nombre_dispositivo: str = Field(..., min_length=1, max_length=100, description="Nombre del dispositivo")
    tipo: str = Field(..., min_length=1, max_length=50, description="Tipo: switch, router, firewall, etc")
    ip: str = Field(..., min_length=7, max_length=50, description="Dirección IP del dispositivo")
    
    # Opcionales
    mac: Optional[str] = Field(None, max_length=50, description="Dirección MAC")
    gateway: Optional[str] = Field(None, max_length=50, description="Gateway del dispositivo")
    vlan: Optional[str] = Field(None, max_length=20, description="VLAN")
    puerto: Optional[str] = Field(None, max_length=50, description="Puerto de conexión")
    dns: Optional[str] = Field(None, max_length=400, description="Servidor DNS")
    ubicacion: Optional[str] = Field(None, max_length=255, description="Ubicación física")
    descripcion: Optional[str] = Field(None, description="Descripción del dispositivo")
    position_x: Optional[float] = Field(None, description="Posición X en el canvas")
    position_y: Optional[float] = Field(None, description="Posición Y en el canvas")
    
    @field_validator('ip')
    @classmethod
    def validate_ip(cls, v: str) -> str:
        """Valida formato de IP básico"""
        ip_pattern = r'^(\d{1,3}\.){3}\d{1,3}$'
        if not re.match(ip_pattern, v):
            raise ValueError('Formato de IP inválido')
        return v
    
    @field_validator('mac')
    @classmethod
    def validate_mac(cls, v: Optional[str]) -> Optional[str]:
        """Valida formato de MAC básico"""
        if v is None:
            return v
        mac_pattern = r'^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$'
        if not re.match(mac_pattern, v):
            raise ValueError('Formato de MAC inválido (debe ser XX:XX:XX:XX:XX:XX o XX-XX-XX-XX-XX-XX)')
        return v.lower()


class DeviceCreate(DeviceBase):
    """Schema para crear un dispositivo"""
    pass


class DeviceUpdate(BaseModel):
    """Schema para actualizar un dispositivo (todos los campos opcionales)"""
    nombre_dispositivo: Optional[str] = Field(None, min_length=1, max_length=100)
    tipo: Optional[str] = Field(None, min_length=1, max_length=50)
    ip: Optional[str] = Field(None, min_length=7, max_length=50)
    mac: Optional[str] = Field(None, max_length=50)
    gateway: Optional[str] = Field(None, max_length=50)
    vlan: Optional[str] = Field(None, max_length=20)
    puerto: Optional[str] = Field(None, max_length=50)
    dns: Optional[str] = Field(None, max_length=400)
    ubicacion: Optional[str] = Field(None, max_length=255)
    descripcion: Optional[str] = None
    position_x: Optional[float] = None
    position_y: Optional[float] = None


class DeviceResponse(DeviceBase):
    """Schema de respuesta con datos completos del dispositivo"""
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)


# ============ DEVICE STATUS SCHEMAS ============

class DeviceStatusBase(BaseModel):
    """Schema base de estado de dispositivo"""
    status: str = Field(..., pattern="^(online|offline|warning)$", description="Estado del dispositivo")
    response_time_ms: Optional[float] = Field(None, ge=0, description="Tiempo de respuesta en ms")
    check_method: Optional[str] = Field(None, pattern="^(icmp|snmp|both)$", description="Método de verificación")
    error_message: Optional[str] = Field(None, description="Mensaje de error si falla")
    snmp_data: Optional[str] = Field(None, description="Datos SNMP en formato JSON")


class DeviceStatusCreate(DeviceStatusBase):
    """Schema para crear un registro de estado"""
    device_id: int


class DeviceStatusResponse(DeviceStatusBase):
    """Schema de respuesta de estado"""
    id: int
    device_id: int
    checked_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


# ============ DEVICE STATUS SUMMARY SCHEMAS ============

class DeviceStatusSummaryResponse(BaseModel):
    """Schema de respuesta del resumen de estado"""
    id: int
    device_id: int
    last_status: str
    last_response_time_ms: Optional[float] = None
    last_check_method: Optional[str] = None
    last_error_message: Optional[str] = None
    last_checked_at: Optional[datetime] = None
    first_seen_online: Optional[datetime] = None
    last_seen_online: Optional[datetime] = None
    last_seen_offline: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    total_checks: Optional[int] = None
    total_failures: Optional[int] = None
    uptime_percentage: Optional[float] = None
    
    model_config = ConfigDict(from_attributes=True)


# ============ DEVICE CONNECTION SCHEMAS ============

class DeviceConnectionBase(BaseModel):
    """Schema base de conexión entre dispositivos"""
    source_device_id: int = Field(..., description="ID del dispositivo origen")
    target_device_id: int = Field(..., description="ID del dispositivo destino")
    connection_label: Optional[str] = Field("sin etiqueta", max_length=100, description="Etiqueta de la conexión")
    connection_type: Optional[str] = Field(None, max_length=20, description="Tipo: entrada, salida, bidireccional")


class DeviceConnectionCreate(DeviceConnectionBase):
    """Schema para crear una conexión"""
    pass


class DeviceConnectionResponse(DeviceConnectionBase):
    """Schema de respuesta de conexión"""
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)


# ============ SCHEMAS COMBINADOS (con relaciones) ============

class DeviceWithStatus(DeviceResponse):
    """Dispositivo con su último estado"""
    status_summary: Optional[DeviceStatusSummaryResponse] = None


class DeviceWithConnections(DeviceResponse):
    """Dispositivo con sus conexiones"""
    outgoing_connections: List[DeviceConnectionResponse] = []
    incoming_connections: List[DeviceConnectionResponse] = []


class DeviceComplete(DeviceResponse):
    """Dispositivo con toda su información (estado + conexiones)"""
    status_summary: Optional[DeviceStatusSummaryResponse] = None
    outgoing_connections: List[DeviceConnectionResponse] = []
    incoming_connections: List[DeviceConnectionResponse] = []


# ============ SCHEMAS PARA FRONTEND (compatibilidad con tu JSON actual) ============

class FrontendPositionData(BaseModel):
    """Posición del nodo en el canvas"""
    x: float
    y: float


class FrontendDeviceData(BaseModel):
    """Datos del dispositivo desde el frontend"""
    ip: str
    mac: Optional[str] = "aa:bb:cc:dd:ee:ff"
    gateway: Optional[str] = None
    vlan: Optional[str] = None
    puerto: Optional[str] = ""
    dns: Optional[str] = None
    ubicacion: Optional[str] = ""
    descripcion: Optional[str] = "dispositivo de red"


class FrontendConnectionInfo(BaseModel):
    """Información de conexión desde el frontend"""
    id: str  # node_id del dispositivo conectado
    label: Optional[str] = "sin etiqueta"
    desde: Optional[str] = None  # Para entradas
    hacia: Optional[str] = None  # Para salidas


class FrontendConectadoA(BaseModel):
    """Objeto conectadoA del frontend"""
    entradas: Optional[List[FrontendConnectionInfo]] = []
    salidas: Optional[List[FrontendConnectionInfo]] = []


class FrontendDeviceCreate(BaseModel):
    """
    Schema compatible con el JSON que envía tu frontend
    Ejemplo:
    {
      "id": "node_1",
      "label": "switch 1",
      "tipo": "switch",
      "posicion": {"x": 328, "y": 156},
      "data": {...},
      "conectadoA": {...}
    }
    """
    id: str  # node_id
    label: str  # nombre_dispositivo
    tipo: str
    posicion: FrontendPositionData
    data: FrontendDeviceData
    conectadoA: Optional[FrontendConectadoA] = None


class BulkDeviceCreate(BaseModel):
    """Schema para crear múltiples dispositivos desde el frontend"""
    devices: List[FrontendDeviceCreate]


# ============ SCHEMAS DE WEBSOCKET ============

class WebSocketStatusUpdate(BaseModel):
    """Actualización de estado enviada por WebSocket"""
    node_id: str
    status: str  # "online" o "offline"
    response_time_ms: Optional[float] = None
    checked_at: datetime
    error_message: Optional[str] = None
    check_method: str


class WebSocketMessage(BaseModel):
    """Mensaje genérico de WebSocket"""
    type: str  # "status_update", "connection", "error"
    data: dict


# ============ SCHEMAS DE VERIFICACIÓN MANUAL ============

class DeviceCheckRequest(BaseModel):
    """Schema para solicitar verificación manual de un dispositivo"""
    check_method: Optional[str] = Field("both", pattern="^(icmp|snmp|both)$")


class DeviceCheckResponse(BaseModel):
    """Respuesta de verificación manual"""
    node_id: str
    nombre_dispositivo: str
    ip: str
    status: str
    response_time_ms: Optional[float] = None
    check_method: str
    error_message: Optional[str] = None
    checked_at: datetime


# ============ SCHEMAS DE HISTÓRICO ============

class DeviceStatusHistoryQuery(BaseModel):
    """Parámetros para consultar histórico de estados"""
    limit: int = Field(100, ge=1, le=1000, description="Cantidad de registros")
    offset: int = Field(0, ge=0, description="Offset para paginación")
    status_filter: Optional[str] = Field(None, pattern="^(online|offline|warning)$")
    from_date: Optional[datetime] = Field(None, description="Fecha inicial")
    to_date: Optional[datetime] = Field(None, description="Fecha final")


class DeviceStatusHistoryResponse(BaseModel):
    """Respuesta de histórico con paginación"""
    total: int
    limit: int
    offset: int
    items: List[DeviceStatusResponse]


# ============ SCHEMAS DE ESTADÍSTICAS ============

class DeviceStatistics(BaseModel):
    """Estadísticas de un dispositivo"""
    device_id: int
    node_id: str
    nombre_dispositivo: str
    total_checks: int
    online_checks: int
    offline_checks: int
    uptime_percentage: float
    avg_response_time_ms: Optional[float] = None
    last_24h_checks: int
    last_24h_online: int


class NetworkStatistics(BaseModel):
    """Estadísticas generales de la red"""
    total_devices: int
    online_devices: int
    offline_devices: int
    warning_devices: int
    avg_network_response_time: Optional[float] = None
    last_check: Optional[datetime] = None


# ============ SCHEMAS DE RESPUESTA GENÉRICOS ============

class MessageResponse(BaseModel):
    """Respuesta genérica con mensaje"""
    message: str
    detail: Optional[str] = None


class ErrorResponse(BaseModel):
    """Respuesta de error"""
    error: str
    detail: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.now)
    
class FrontendConnectionInfo(BaseModel):
    """Información de conexión desde el frontend"""
    id: str  # node_id del dispositivo conectado
    label: Optional[str] = "sin etiqueta"
    desde: Optional[str] = None  # Para entradas (node_id origen)
    hacia: Optional[str] = None  # Para salidas (node_id destino)


class FrontendConectadoA(BaseModel):
    """Objeto conectadoA del frontend"""
    entradas: Optional[List[FrontendConnectionInfo]] = []
    salidas: Optional[List[FrontendConnectionInfo]] = []