from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List
from contextlib import asynccontextmanager
from datetime import datetime
import asyncio
import time

# Importaciones locales
from app.database import get_db, SessionLocal
from app import schemas, models  # Agregar models si lo necesitas
from app.servicios.device_service import DeviceService
from app.servicios.estatus_service import StatusService
from app.servicios.monitor_red import verificar_dispositivo
from app.utils.websocket_manager import ConnectionManager

# Variables globales
monitoring_task = None
websocket_manager = None



# ============ TAREA DE MONITOREO EN SEGUNDO PLANO ============

INTERVALO_SONDEO_S = 30   # cada cuánto se verifica toda la red

# Último estado conocido de cada equipo: {node_id: "online" | "offline"}
# Sirve para avisar por WebSocket solo cuando algo CAMBIA.
estados_previos = {}


def cargar_estados_previos():
    """Al arrancar, toma el último estado guardado para no anunciar todo como 'cambio'."""
    db = SessionLocal()
    try:
        for item in DeviceService.get_devices_with_status(db):
            if item["status"]:
                estados_previos[item["device"].node_id] = item["status"].last_status
    finally:
        db.close()


async def ciclo_de_sondeo():
    """Verifica todos los dispositivos una vez, guarda los resultados y avisa los cambios."""
    # 1. Leer la lista de equipos (y cerrar la sesión antes de la parte lenta)
    db = SessionLocal()
    try:
        dispositivos = [
            (d.id, d.node_id, d.nombre_dispositivo, d.ip)
            for d in DeviceService.get_all_devices(db)
        ]
    finally:
        db.close()

    if not dispositivos:
        print("No hay dispositivos para verificar")
        return

    print("\n" + "═" * 64)
    print(f" SONDEO {datetime.now():%H:%M:%S} · {len(dispositivos)} dispositivo(s)")
    print("═" * 64 + "\n")
    inicio = time.perf_counter()

    # 2. Verificar todos en paralelo
    resultados = await asyncio.gather(
        *(verificar_dispositivo(ip, nombre) for (_, _, nombre, ip) in dispositivos)
    )

    # 3. Guardar y detectar cambios
    cambios = []
    db = SessionLocal()
    try:
        for (device_id, node_id, nombre, ip), resultado in zip(dispositivos, resultados):
            try:
                StatusService.save_device_status(db, device_id, resultado)
            except Exception as e:
                db.rollback()
                print(f" No se pudo guardar el estado de {nombre}: {e}")
                continue

            anterior = estados_previos.get(node_id)
            estados_previos[node_id] = resultado["status"]
            if anterior != resultado["status"]:
                cambios.append({
                    "type": "status_update",
                    "data": {
                        "node_id": node_id,
                        "nombre_dispositivo": nombre,
                        "ip": ip,
                        "status": resultado["status"],
                        "previous_status": anterior,
                        "response_time_ms": resultado["response_time_ms"],
                        "check_method": resultado["check_method"],
                        "checked_at": datetime.now().isoformat(),
                        "error_message": resultado["error_message"],
                    },
                })
    finally:
        db.close()

    en_linea = sum(1 for r in resultados if r["status"] == "online")
    print("─" * 64)
    print(
        f" {en_linea} en línea · {len(resultados) - en_linea} fuera de línea · "
        f"{len(cambios)} cambio(s) · {time.perf_counter() - inicio:.1f} s"
    )
    for cambio in cambios:
        d = cambio["data"]
        antes = d["previous_status"] or "nuevo"
        print(f"   ↳ {d['nombre_dispositivo']}: {antes} → {d['status']}")
    print("═" * 64)

    # 4. Avisar solo los cambios
    if cambios and websocket_manager:
        for cambio in cambios:
            await websocket_manager.broadcast(cambio)


async def tarea_monitoreo():
    """Repite el sondeo cada INTERVALO_SONDEO_S segundos mientras la API esté viva."""
    print(f" -> Monitoreo en segundo plano: cada {INTERVALO_SONDEO_S} s")
    cargar_estados_previos()
    while True:
        try:
            await ciclo_de_sondeo()
        except Exception as e:
            # Un error en un ciclo no debe matar el monitoreo
            print(f"Error en el ciclo de monitoreo: {e}")
        await asyncio.sleep(INTERVALO_SONDEO_S)



















@asynccontextmanager
async def lifespan(app: FastAPI):
    """Maneja eventos de inicio y cierre de la aplicación"""
    global monitoring_task, websocket_manager
    
    # Startup
    print("=" * 60)
    print("Iniciando API Admin Red")
    print("=" * 60)
    print(" Base de datos: PostgreSQL")
    print("Python: 3.12")
    print("FastAPI v3.0.0")
    print("=" * 60)
    
    websocket_manager = ConnectionManager()
    monitoring_task = asyncio.create_task(tarea_monitoreo())
    print(" Tarea de monitoreo iniciada\n")
    
    yield  # La aplicación corre aquí
    
    # Shutdown
    print("\n" + "=" * 60)
    print("Cerrando API Admin Red...")
    print("=" * 60)
    
    if monitoring_task:
        monitoring_task.cancel()
        try:
            await monitoring_task
        except asyncio.CancelledError:
            print(" Tarea de monitoreo cancelada")
    
    print("Chao pescao!\n")


# ============ CONFIGURACIÓN DE FASTAPI ============

app = FastAPI(
    title="Admin Red API",
    description="API para administración y monitoreo de dispositivos de red con SNMP/ICMP",
    version="3.0.0",
    lifespan=lifespan
)

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============ RUTAS - GENERAL ============

@app.get("/", tags=["General"])
async def root():
    """Información de la API"""
    return {
        "message": "API Admin Red con PostgreSQL",
        "version": "Beta 1.0.0",
        "database": "PostgreSQL",
        "endpoints": {
            "docs": "/docs",
            "websocket": "ws://localhost:8080/ws",
            "devices": "/api/devices"
        }
    }


@app.get("/api/health", tags=["General"])
async def health_check(db: Session = Depends(get_db)):
    """Verifica el estado de la API y la base de datos"""
    try:
        # Intenta hacer una consulta simple
        DeviceService.get_all_devices(db)
        return {
            "status": "healthy",
            "database": "connected",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database error: {str(e)}")


# ============ RUTAS - DISPOSITIVOS ============

@app.get("/api/devices", response_model=List[schemas.DeviceWithStatus], tags=["Dispositivos"])
async def get_all_devices(db: Session = Depends(get_db)):
    """
    Obtiene todos los dispositivos con su último estado
    """
    devices_with_status = DeviceService.get_devices_with_status(db)
    
    result = []
    for item in devices_with_status:
        device_data = schemas.DeviceResponse.model_validate(item["device"])
        status_data = schemas.DeviceStatusSummaryResponse.model_validate(item["status"]) if item["status"] else None
        
        result.append(schemas.DeviceWithStatus(
            **device_data.model_dump(),
            status_summary=status_data
        ))
    
    return result




@app.post("/api/devices/bulk")
async def bulk_create_devices(
    bulk_data: schemas.BulkDeviceCreate,
    db: Session = Depends(get_db)
):
    """
    Crea o actualiza múltiples dispositivos EN LOTE
    Y sincroniza (elimina dispositivos que ya no existen)
    """
    created = 0
    updated = 0
    deleted = 0
    errors = []

    try:
        # ============================================
        # PASO 1: SINCRONIZAR (ELIMINAR los que no existen)
        # ============================================
        frontend_node_list = [
            {"id": device.id, "label": device.label}
            for device in bulk_data.devices
        ]
        
        sync_result = DeviceService.sync_all_devices(db, frontend_node_list)
        deleted = sync_result["deleted"]
        
        # ============================================
        # PASO 2: CREAR/ACTUALIZAR DISPOSITIVOS
        # ============================================
        for device_data in bulk_data.devices:
            try:
                # Buscar si ya existe
                existing_device = db.query(models.Device).filter(
                    models.Device.node_id == device_data.id
                ).first()

                # Extraer datos base
                device_dict = {
                    "node_id": device_data.id,
                    "nombre_dispositivo": device_data.label,
                    "tipo": device_data.tipo,
                    "position_x": device_data.posicion.x,
                    "position_y": device_data.posicion.y,
                    "ip": device_data.data.ip if device_data.data.ip else None,
                    "mac": device_data.data.mac if device_data.data.mac else None,
                    "gateway": device_data.data.gateway if device_data.data.gateway else None,
                    "vlan": device_data.data.vlan if device_data.data.vlan else None,
                    "puerto": device_data.data.puerto if device_data.data.puerto else None,
                    "dns": device_data.data.dns if device_data.data.dns else None,
                    "ubicacion": device_data.data.ubicacion if device_data.data.ubicacion else None,
                    "descripcion": device_data.data.descripcion if device_data.data.descripcion else None,
                }

                if existing_device:
                    # ACTUALIZAR dispositivo existente
                    for key, value in device_dict.items():
                        if key != "node_id":  # No actualizar el ID
                            setattr(existing_device, key, value)
                    updated += 1
                    print(f"Actualizando: {device_data.id}")
                else:
                    # CREAR nuevo dispositivo
                    new_device = models.Device(**device_dict)
                    db.add(new_device)
                    created += 1
                    print(f"Creando: {device_data.id}")

            except Exception as e:
                errors.append({
                    "device_id": device_data.id,
                    "error": str(e)
                })
                print(f" Error en {device_data.id}: {str(e)}")

        # Guardar cambios
        db.commit()

        return {
            "message": "Dispositivos procesados exitosamente",
            "statistics": {
                "created": created,
                "updated": updated,
                "deleted": deleted,
                "total_received": len(bulk_data.devices),
                "errors": len(errors),
            },
            "error_details": errors if errors else None
        }

    except Exception as e:
        db.rollback()
        print(f" Error crítico: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/connections/sync")
async def sync_connections(
    edges_data: dict,
    db: Session = Depends(get_db)
):
    """
    Sincroniza las conexiones entre frontend y base de datos:
    - Elimina conexiones que ya no existen
    - Crea conexiones nuevas
    
    Body esperado:
    {
        "edges": [
            {"source": "node_1", "target": "node_2", "label": "conexión 1"},
            {"source": "node_2", "target": "node_3", "label": "conexión 2"}
        ]
    }
    """
    try:
        edges = edges_data.get("edges", [])
        
        if not isinstance(edges, list):
            raise HTTPException(
                status_code=400, 
                detail="El campo 'edges' debe ser una lista"
            )
        
        # Llamar al servicio de sincronización
        result = DeviceService.sync_all_connections(db, edges)
        
        return {
            "message": " Conexiones sincronizadas exitosamente",
            "statistics": result
        }
        
    except Exception as e:
        db.rollback()
        print(f" Error en sincronización: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail=f"Error al sincronizar conexiones: {str(e)}"
        )


@app.get("/api/connections", response_model=List[dict], tags=["Conexiones"])
async def get_all_connections(db: Session = Depends(get_db)):
    """
    Obtiene todas las conexiones de la red
    
    **Formato de respuesta:**
```json
    [
      {
        "id": 1,
        "source": {
          "node_id": "node_1",
          "nombre": "Switch 1",
          "ip": "192.168.1.1"
        },
        "target": {
          "node_id": "node_2",
          "nombre": "Switch 2",
          "ip": "192.168.1.2"
        },
        "label": "conexión principal",
        "type": "salida"
      }
    ]
```
    """
    connections = DeviceService.get_all_connections(db)
    return connections


@app.get("/api/devices/{device_id}/connections", tags=["Conexiones"])
async def get_device_connections(device_id: int, db: Session = Depends(get_db)):
    """
    Obtiene las conexiones de un dispositivo específico
    """
    device = DeviceService.get_device_by_id(db, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado")
    
    connections = DeviceService.get_device_connections(db, device_id)
    
    return {
        "device": schemas.DeviceResponse.model_validate(device),
        "connections": {
            "outgoing": [schemas.DeviceConnectionResponse.model_validate(c) for c in connections["outgoing"]],
            "incoming": [schemas.DeviceConnectionResponse.model_validate(c) for c in connections["incoming"]]
        }
    }





# ============ RUTAS - VERIFICACIÓN DE ESTADO ============

@app.post("/api/devices/{device_id}/check", response_model=schemas.DeviceCheckResponse, tags=["Estado"])
async def check_device_manual(
    device_id: int,
    check_request: schemas.DeviceCheckRequest,
    db: Session = Depends(get_db)
):
    """
    Verifica manualmente el estado de un dispositivo específico
    
    - **check_method**: "icmp" (ping), "snmp", o "both" (ambos)
    """
    device = DeviceService.get_device_by_id(db, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado")
    
    print(f"🔍 Verificación manual de {device.nombre_dispositivo} ({device.ip})")
    
    # Realizar verificación
    check_result = await verificar_dispositivo(device.ip, device.nombre_dispositivo)
    estados_previos[device.node_id] = check_result["status"]
    
    # Guardar en BD
    StatusService.save_device_status(db, device.id, check_result)
    
    # Enviar actualización por WebSocket
    if websocket_manager and websocket_manager.active_connections:
        await websocket_manager.broadcast({
            "type": "status_update",
            "data": {
                "node_id": device.node_id,
                "nombre_dispositivo": device.nombre_dispositivo,
                "ip": device.ip,
                "status": check_result["status"],
                "response_time_ms": check_result.get("response_time_ms"),
                "check_method": check_result["check_method"],
                "checked_at": datetime.now().isoformat(),
                "error_message": check_result.get("error_message")
            }
        })
    
    return schemas.DeviceCheckResponse(
        node_id=device.node_id,
        nombre_dispositivo=device.nombre_dispositivo,
        ip=device.ip,
        status=check_result["status"],
        response_time_ms=check_result.get("response_time_ms"),
        check_method=check_result["check_method"],
        error_message=check_result.get("error_message"),
        checked_at=datetime.now()
    )


@app.get("/api/devices/{device_id}/status-history", response_model=schemas.DeviceStatusHistoryResponse, tags=["Estado"])
async def get_device_status_history(
    device_id: int,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """
    Obtiene el histórico de estados de un dispositivo
    
    - **limit**: Cantidad de registros (máx 1000)
    - **offset**: Para paginación
    """
    device = DeviceService.get_device_by_id(db, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado")
    
    history, total = StatusService.get_device_status_history(db, device_id, limit, offset)
    
    return schemas.DeviceStatusHistoryResponse(
        total=total,
        limit=limit,
        offset=offset,
        items=[schemas.DeviceStatusResponse.model_validate(item) for item in history]
    )


@app.get("/api/statistics", response_model=schemas.NetworkStatistics, tags=["Estadísticas"])
async def get_network_statistics(db: Session = Depends(get_db)):
    """
    Obtiene estadísticas generales de la red
    """
    stats = StatusService.get_network_statistics(db)
    return schemas.NetworkStatistics(**stats)


# ============ WEBSOCKET ENDPOINT ============

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    Endpoint WebSocket para recibir actualizaciones de estado en tiempo real
    
    **Mensajes que recibirás:**
```json
    {
      "type": "status_update",
      "data": {
        "node_id": "node_1",
        "nombre_dispositivo": "Switch 1",
        "ip": "192.168.1.1",
        "status": "online",
        "response_time_ms": 15.5,
        "check_method": "snmp",
        "checked_at": "2025-11-10T12:00:00",
        "error_message": null
      }
    }
```
    """
    await websocket_manager.connect(websocket)
    
    try:
        # Enviar mensaje de bienvenida
        await websocket.send_json({
            "type": "connection",
            "message": "bellaco, esta conectado al sistema de monitoreo",
            "timestamp": datetime.now().isoformat()
        })
        
        # Mantener la conexión abierta
        while True:
            # Recibir mensajes del cliente (opcional, para ping/pong)
            data = await websocket.receive_json()
            
            # Responder a ping
            if data.get("type") == "ping":
                await websocket.send_json({
                    "type": "pong",
                    "timestamp": datetime.now().isoformat()
                })
                
    except WebSocketDisconnect:
        websocket_manager.disconnect(websocket)
    except Exception as e:
        print(f"Error en WebSocket: {e}")
        websocket_manager.disconnect(websocket)


# ============ EJECUTAR SERVIDOR ============

if __name__ == "__main__":
    import uvicorn
    
    print("\n" + "=" * 60)
    print("qlq pa se está Iniciando servidor der baquen")
    print("=" * 60)
    print("URL: http://localhost:8080")
    print("Documentación pa ver como van las apis: http://localhost:8080/docs")
    print(" Er WebSocket: ws://localhost:8080/ws")
    print("=" * 60 + "\n")
    
    uvicorn.run(
        "app.main:app",
        host="localhost",
        port=8080,
        reload=True,
        log_level="info"
    )