from sqlalchemy import Column, Integer, String, DateTime, Float, ForeignKey, Text, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class Device(Base):
    """Modelo de dispositivo de red"""
    __tablename__ = "devices"
    
    # Identificadores
    id = Column(Integer, primary_key=True, index=True)
    node_id = Column(String(50), unique=True, nullable=False, index=True)  # "node_1", "node_2"
    nombre_dispositivo = Column(String(100), nullable=False)  # "switch 1", "Router Principal"
    tipo = Column(String(50), nullable=False)  # "switch", "router", "firewall"
    ip = Column(String(50), unique=True, nullable=False, index=True)
    mac = Column(String(50))
    gateway = Column(String(50))
    vlan = Column(String(20))
    puerto = Column(String(50))
    dns = Column(String(400))
    ubicacion = Column(String(255))
    descripcion = Column(Text)
    position_x = Column(Float)  # Posición X en el canvas
    position_y = Column(Float)  # Posición Y en el canvas
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relaciones
    status_history = relationship("DeviceStatus", back_populates="device", cascade="all, delete-orphan")
    status_summary = relationship("DeviceStatusSummary", back_populates="device", uselist=False, cascade="all, delete-orphan")
    
    # Conexiones salientes
    outgoing_connections = relationship(
        "DeviceConnection",
        foreign_keys="DeviceConnection.source_device_id",
        back_populates="source_device",
        cascade="all, delete-orphan"
    )
    
    # Conexiones entrantes
    incoming_connections = relationship(
        "DeviceConnection",
        foreign_keys="DeviceConnection.target_device_id",
        back_populates="target_device",
        cascade="all, delete-orphan"
    )
    
    def __repr__(self):
        return f"<Device(node_id={self.node_id}, nombre={self.nombre_dispositivo}, ip={self.ip})>"


class DeviceStatus(Base):
    """Histórico de estados de dispositivos"""
    __tablename__ = "device_status"
    
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Estado
    status = Column(String(20), nullable=False)  # "online", "offline", "warning"
    response_time_ms = Column(Float)  # Tiempo de respuesta en milisegundos
    
    # Método de verificación
    check_method = Column(String(20))  # "icmp", "snmp", "both"
    
    # Información adicional
    error_message = Column(Text)  # Mensaje de error si falla
    snmp_data = Column(Text)  # JSON con datos SNMP adicionales (opcional)
    
    # Timestamp
    checked_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    
    # Relación
    device = relationship("Device", back_populates="status_history")
    
    # Índice compuesto para consultas rápidas
    __table_args__ = (
        Index('idx_device_checked', 'device_id', 'checked_at'),
    )
    
    def __repr__(self):
        return f"<DeviceStatus(device_id={self.device_id}, status={self.status}, checked_at={self.checked_at})>"


class DeviceStatusSummary(Base):
    """Resumen del último estado de cada dispositivo (caché)"""
    __tablename__ = "device_status_summary"
    
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("devices.id", ondelete="CASCADE"), unique=True, nullable=False)
    
    # Último estado conocido
    last_status = Column(String(20), nullable=False, index=True)  # "online", "offline"
    last_response_time_ms = Column(Float)
    last_check_method = Column(String(20))
    last_error_message = Column(Text)
    
    # Timestamps
    last_checked_at = Column(DateTime(timezone=True))
    first_seen_online = Column(DateTime(timezone=True))
    last_seen_online = Column(DateTime(timezone=True))
    last_seen_offline = Column(DateTime(timezone=True))

    total_checks = Column(Integer, nullable=False, server_default="0", default=0)
    total_failures = Column(Integer, nullable=False, server_default="0", default=0)
    uptime_percentage = Column(Float)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relación
    device = relationship("Device", back_populates="status_summary")
    
    def __repr__(self):
        return f"<DeviceStatusSummary(device_id={self.device_id}, last_status={self.last_status})>"


class DeviceConnection(Base):
    """Conexiones entre dispositivos (topología de red)"""
    __tablename__ = "device_connections"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Dispositivos conectados
    source_device_id = Column(Integer, ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True)
    target_device_id = Column(Integer, ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Información de la conexión
    connection_label = Column(String(100), default="sin etiqueta")
    connection_type = Column(String(20))  # "entrada", "salida", "bidireccional"
    
    source_handle = Column(String(20))  # "top-out", "bottom-out", "left-out", "right-out"
    target_handle = Column(String(20))  # "top-in", "bottom-in", "left-in", "right-in"
    
    
    # Timestamp
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relaciones
    source_device = relationship("Device", foreign_keys=[source_device_id], back_populates="outgoing_connections")
    target_device = relationship("Device", foreign_keys=[target_device_id], back_populates="incoming_connections")
    
    # Índice compuesto para evitar conexiones duplicadas
    __table_args__ = (
        Index('idx_connection_unique', 'source_device_id', 'target_device_id'),
    )
    
    def __repr__(self):
        return f"<DeviceConnection(source={self.source_device_id}, target={self.target_device_id})>"