from sqlalchemy.orm import Session
from sqlalchemy import select
from typing import List, Optional, Dict
from app import models, schemas


class DeviceService:
    """Servicio para operaciones CRUD de dispositivos"""
    
    @staticmethod
    def get_all_devices(db: Session) -> List[models.Device]:
        """Obtiene todos los dispositivos"""
        return db.query(models.Device).all()
    
    @staticmethod
    def get_device_by_node_id(db: Session, node_id: str) -> Optional[models.Device]:
        """Obtiene un dispositivo por node_id"""
        return db.query(models.Device).filter(models.Device.node_id == node_id).first()
    
    @staticmethod
    def get_devices_with_status(db: Session) -> List[dict]:
        """Obtiene todos los dispositivos con su último estado"""
        devices = db.query(models.Device).all()
        result = []
        
        for device in devices:
            device_dict = {
                "device": device,
                "status": db.query(models.DeviceStatusSummary).filter(
                    models.DeviceStatusSummary.device_id == device.id
                ).first()
            }
            result.append(device_dict)
        
        return result
    
    @staticmethod
    def sync_all_devices(db: Session, frontend_nodes: List[dict]) -> dict:
        """
        Sincroniza dispositivos: elimina los que ya no existen y crea/actualiza los demás
        
        Args:
            db: Sesión de base de datos
            frontend_nodes: Lista de dispositivos desde React Flow
                Ejemplo: [{"id": "node_1", "label": "Switch 1", ...}]
        
        Returns:
            dict: Estadísticas de la sincronización
        """
        
        # 1️⃣ Obtener todos los node_ids del frontend
        frontend_node_ids = {node.get("id") for node in frontend_nodes if node.get("id")}
        print(f" Dispositivos en frontend: {len(frontend_node_ids)}")
        
        # 2️⃣ Obtener todos los dispositivos de la BD
        db_devices = db.query(models.Device).all()
        print(f"Dispositivos en BD: {len(db_devices)}")
        
        # 3️⃣ ELIMINAR dispositivos que ya NO están en el frontend
        deleted_count = 0
        for device in db_devices:
            if device.node_id not in frontend_node_ids:
                print(f"Eliminando dispositivo: {device.node_id} ({device.nombre_dispositivo})")
                db.delete(device)
                deleted_count += 1
        
        # Guardar eliminaciones
        if deleted_count > 0:
            db.commit()
        
        print(f" Dispositivos eliminados: {deleted_count}")
        
        return {
            "deleted": deleted_count,
            "frontend_total": len(frontend_node_ids)
        }

    @staticmethod
    def create_devices_bulk(
        db: Session, 
        devices_data: List[schemas.FrontendDeviceCreate]
    ) -> tuple[List[models.Device], List[dict]]:
        """
        Crea múltiples dispositivos desde el frontend
        Retorna: (dispositivos_creados, errores)
        """
        created_devices = []
        errors = []
        
        for frontend_device in devices_data:
            try:
                device_data = schemas.DeviceCreate(
                    node_id=frontend_device.id,
                    nombre_dispositivo=frontend_device.label,
                    tipo=frontend_device.tipo,
                    ip=frontend_device.data.ip,
                    mac=frontend_device.data.mac,
                    gateway=frontend_device.data.gateway,
                    vlan=frontend_device.data.vlan,
                    puerto=frontend_device.data.puerto,
                    dns=frontend_device.data.dns,  #  CORREGIDO (era DNS en mayúscula)
                    ubicacion=frontend_device.data.ubicacion,
                    descripcion=frontend_device.data.descripcion,
                    position_x=frontend_device.posicion.x,
                    position_y=frontend_device.posicion.y
                )
                
                # Verificar duplicados
                existing = db.query(models.Device).filter(
                    (models.Device.node_id == device_data.node_id) | 
                    (models.Device.ip == device_data.ip)
                ).first()
                
                if existing:
                    errors.append({
                        "node_id": device_data.node_id,
                        "error": "Dispositivo duplicado (node_id o IP ya existe)"
                    })
                    continue
                
                db_device = models.Device(**device_data.model_dump())
                db.add(db_device)
                created_devices.append(db_device)
                
            except Exception as e:
                errors.append({
                    "node_id": frontend_device.id,
                    "error": str(e)
                })
                db.rollback()
        
        if created_devices:
            db.commit()
        
        return created_devices, errors
    
    @staticmethod
    def create_or_update_devices_bulk(
        db: Session, 
        devices_data: List[schemas.FrontendDeviceCreate]
    ) -> tuple[List[models.Device], List[dict], dict]:
        """
        Crea o actualiza múltiples dispositivos desde el frontend
        También procesa las conexiones entre dispositivos
        
        Retorna: (dispositivos_procesados, errores, estadísticas)
        """
        processed_devices = []
        errors = []
        stats = {
            "created": 0,
            "updated": 0,
            "connections_created": 0,
            "connections_errors": 0
        }
        
        # Mapeo de node_id a device_id para procesar conexiones después
        node_to_device_id = {}
        
        # FASE 1: Crear o actualizar dispositivos
        for frontend_device in devices_data:
            try:
                # Convertir formato frontend a formato BD
                device_data = schemas.DeviceCreate(
                    node_id=frontend_device.id,
                    nombre_dispositivo=frontend_device.label,
                    tipo=frontend_device.tipo,
                    ip=frontend_device.data.ip,
                    mac=frontend_device.data.mac,
                    gateway=frontend_device.data.gateway,
                    vlan=frontend_device.data.vlan,
                    puerto=frontend_device.data.puerto,
                    dns=frontend_device.data.dns,  #  YA ESTABA CORRECTO AQUÍ
                    ubicacion=frontend_device.data.ubicacion,
                    descripcion=frontend_device.data.descripcion,
                    position_x=frontend_device.posicion.x,
                    position_y=frontend_device.posicion.y
                )
                
                # Buscar si existe por node_id
                existing_device = db.query(models.Device).filter(
                    models.Device.node_id == device_data.node_id
                ).first()
                
                if existing_device:
                    # ACTUALIZAR dispositivo existente
                    update_data = device_data.model_dump(exclude={'node_id'})
                    for field, value in update_data.items():
                        setattr(existing_device, field, value)
                    
                    db.commit()
                    db.refresh(existing_device)
                    
                    processed_devices.append(existing_device)
                    node_to_device_id[frontend_device.id] = existing_device.id
                    stats["updated"] += 1
                    
                    print(f"🔄 Dispositivo actualizado: {existing_device.nombre_dispositivo}")
                    
                else:
                    # Verificar IP duplicada antes de crear
                    ip_exists = db.query(models.Device).filter(
                        models.Device.ip == device_data.ip
                    ).first()
                    
                    if ip_exists:
                        errors.append({
                            "node_id": frontend_device.id,
                            "error": f"IP {device_data.ip} ya existe en {ip_exists.nombre_dispositivo}"
                        })
                        continue
                    
                    # CREAR nuevo dispositivo
                    new_device = models.Device(**device_data.model_dump())
                    db.add(new_device)
                    db.commit()
                    db.refresh(new_device)
                    
                    processed_devices.append(new_device)
                    node_to_device_id[frontend_device.id] = new_device.id
                    stats["created"] += 1
                    
                    print(f" Dispositivo creado: {new_device.nombre_dispositivo}")
                    
            except Exception as e:
                errors.append({
                    "node_id": frontend_device.id,
                    "error": str(e)
                })
                print(f" Error procesando {frontend_device.id}: {str(e)}")
                db.rollback()
        
        return processed_devices, errors, stats
    
    @staticmethod
    def get_device_connections(db: Session, device_id: int) -> dict:
        """
        Obtiene todas las conexiones de un dispositivo
        
        Retorna: {
            "outgoing": [...],  # Conexiones salientes
            "incoming": [...]   # Conexiones entrantes
        }
        """
        device = db.query(models.Device).filter(models.Device.id == device_id).first()
        if not device:
            return {"outgoing": [], "incoming": []}
        
        # Conexiones salientes
        outgoing = db.query(models.DeviceConnection).filter(
            models.DeviceConnection.source_device_id == device_id
        ).all()
        
        # Conexiones entrantes
        incoming = db.query(models.DeviceConnection).filter(
            models.DeviceConnection.target_device_id == device_id
        ).all()
        
        return {
            "outgoing": outgoing,
            "incoming": incoming
        }

    @staticmethod
    def get_all_connections(db: Session) -> List[dict]:
        """
        Obtiene todas las conexiones de la red en formato para el frontend
        """
        connections = db.query(models.DeviceConnection).all()
        
        result = []
        for conn in connections:
            source_device = db.query(models.Device).filter(
                models.Device.id == conn.source_device_id
            ).first()
            
            target_device = db.query(models.Device).filter(
                models.Device.id == conn.target_device_id
            ).first()
            
            if source_device and target_device:
                result.append({
                    "id": conn.id,
                    "source": {
                        "node_id": source_device.node_id,
                        "nombre": source_device.nombre_dispositivo,
                        "ip": source_device.ip
                    },
                    "target": {
                        "node_id": target_device.node_id,
                        "nombre": target_device.nombre_dispositivo,
                        "ip": target_device.ip
                    },
                    "connection_label": conn.connection_label,  
                    "source_handle": conn.source_handle,        
                    "target_handle": conn.target_handle,        
                    "type": conn.connection_type
                })
        
        return result
    
    @staticmethod
    def delete_device(db: Session, device_id: int) -> bool:
        """Elimina un dispositivo"""
        device = db.query(models.Device).filter(models.Device.id == device_id).first()
        if not device:
            return False
        
        db.delete(device)
        db.commit()
        return True
    
    @staticmethod
    def sync_all_connections(db: Session, frontend_edges: List[dict]) -> dict:
        """
        Sincroniza TODAS las conexiones de la red con el frontend
        INCLUYENDO los handles (posiciones de conexión)
        
        Args:
            db: Sesión de base de datos
            frontend_edges: Lista de edges desde React Flow
                Ejemplo: [
                    {
                        "source": "node_1", 
                        "target": "node_2", 
                        "label": "conexión 1",
                        "sourceHandle": "right-out",
                        "targetHandle": "left-in"
                    }
                ]
        
        Returns:
            dict: Estadísticas de la sincronización
        """
        
        # 1 Obtener TODAS las conexiones actuales de la BD
        current_connections = db.query(models.DeviceConnection).all()
        print(f" Conexiones actuales en BD: {len(current_connections)}")
        
        # 2  Crear set de tuplas (source, target, sourceHandle, targetHandle)
        frontend_connections = set()
        edge_details = {}
        
        for edge in frontend_edges:
            source_id = edge.get("source")
            target_id = edge.get("target")
            source_handle = edge.get("sourceHandle") or ""
            target_handle = edge.get("targetHandle") or ""
            
            if source_id and target_id:
                key = (source_id, target_id, source_handle, target_handle)
                frontend_connections.add(key)
                
                # Guardar detalles adicionales
                edge_details[key] = {
                    "label": edge.get("label", "sin etiqueta"),
                    "sourceHandle": source_handle,
                    "targetHandle": target_handle
                }
                
                print(f" Frontend: {source_id}[{source_handle}] → {target_id}[{target_handle}]")
        
        print(f" Conexiones en frontend: {len(frontend_connections)}")
        
        # 3 ELIMINAR conexiones que ya NO existen en el frontend
        deleted_count = 0
        for conn in current_connections:
            #  CREAR CLAVE incluyendo handles
            key = (
                conn.source_device.node_id, 
                conn.target_device.node_id,
                conn.source_handle or "",
                conn.target_handle or ""
            )
            
            if key not in frontend_connections:
                print(f" Eliminando: {conn.source_device.node_id}[{conn.source_handle}] → {conn.target_device.node_id}[{conn.target_handle}]")
                db.delete(conn)
                deleted_count += 1
        
        # 4 CREAR nuevas conexiones que no existen en BD
        created_count = 0
        for key in frontend_connections:
            source_node_id, target_node_id, source_handle, target_handle = key
            
            # Buscar los dispositivos en BD
            source_device = db.query(models.Device).filter(
                models.Device.node_id == source_node_id
            ).first()
            
            target_device = db.query(models.Device).filter(
                models.Device.node_id == target_node_id
            ).first()
            
            if not source_device or not target_device:
                print(f"⚠️ Dispositivo no encontrado: {source_node_id} o {target_node_id}")
                continue
            
            #  VERIFICAR EXISTENCIA incluyendo handles
            exists = db.query(models.DeviceConnection).filter(
                models.DeviceConnection.source_device_id == source_device.id,
                models.DeviceConnection.target_device_id == target_device.id,
                models.DeviceConnection.source_handle == source_handle,
                models.DeviceConnection.target_handle == target_handle
            ).first()
            
            if not exists:
                # Obtener detalles del edge
                details = edge_details[key]
                
                # CREAR con handles
                new_conn = models.DeviceConnection(
                    source_device_id=source_device.id,
                    target_device_id=target_device.id,
                    connection_label=details["label"],
                    connection_type="bidireccional",
                    source_handle=details["sourceHandle"],
                    target_handle=details["targetHandle"]
                )
                db.add(new_conn)
                created_count += 1
                print(f" Creando: {source_node_id}[{source_handle}] → {target_node_id}[{target_handle}]")
        
        # 5 Guardar cambios en BD
        db.commit()
        
        print(f"\n Resumen:")
        print(f"    Creadas: {created_count}")
        print(f"    Eliminadas: {deleted_count}")
        print(f"   Total en frontend: {len(frontend_connections)}")
        
        return {
            "connections_created": created_count,
            "connections_deleted": deleted_count,
            "total_frontend": len(frontend_connections),
            "total_in_db": len(frontend_connections)
        }