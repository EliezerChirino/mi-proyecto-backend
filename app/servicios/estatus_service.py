from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
from app import models, schemas


class StatusService:
    """Servicio para operaciones de estado de dispositivos"""
    
    @staticmethod
    def get_device_status_summary(db: Session, device_id: int) -> Optional[models.DeviceStatusSummary]:
        """Obtiene el resumen de estado de un dispositivo"""
        return db.query(models.DeviceStatusSummary).filter(
            models.DeviceStatusSummary.device_id == device_id
        ).first()
    
    @staticmethod
    def get_device_status_history(
        db: Session,
        device_id: int,
        limit: int = 100,
        offset: int = 0
    ) -> tuple[List[models.DeviceStatus], int]:
        """
        Obtiene el histórico de estados de un dispositivo
        Retorna: (lista_estados, total)
        """
        total = db.query(models.DeviceStatus).filter(
            models.DeviceStatus.device_id == device_id
        ).count()
        
        history = db.query(models.DeviceStatus).filter(
            models.DeviceStatus.device_id == device_id
        ).order_by(models.DeviceStatus.checked_at.desc()).offset(offset).limit(limit).all()
        
        return history, total
    
    @staticmethod
    def save_device_status(db: Session, device_id: int, check_result: dict) -> models.DeviceStatus:
        """
        Guarda un nuevo registro de estado y actualiza el resumen
        
        Args:
            db: Sesión de base de datos
            device_id: ID del dispositivo
            check_result: Resultado de la verificación con keys:
                - status: "online" o "offline"
                - response_time_ms: float opcional
                - check_method: "icmp", "snmp" o "both"
                - error_message: str opcional
                - snmp_data: str opcional
        
        Returns:
            El registro de DeviceStatus creado
        """
        # Crear registro en histórico
        status_record = models.DeviceStatus(
            device_id=device_id,
            status=check_result["status"],
            response_time_ms=check_result.get("response_time_ms"),
            check_method=check_result["check_method"],
            error_message=check_result.get("error_message"),
            snmp_data=check_result.get("snmp_data")
        )
        db.add(status_record)
        
        # Actualizar o crear resumen
        StatusService._update_status_summary(db, device_id, check_result)
        
        db.commit()
        db.refresh(status_record)
        return status_record
    
    @staticmethod
    def _update_status_summary(db: Session, device_id: int, check_result: dict):
        """Actualiza el resumen de estado de un dispositivo (método privado)"""
        summary = db.query(models.DeviceStatusSummary).filter(
            models.DeviceStatusSummary.device_id == device_id
        ).first()
        
        now = datetime.now()
        
        if not summary:
            # Crear nuevo resumen
            summary = models.DeviceStatusSummary(
                device_id=device_id,
                last_status=check_result["status"],
                last_response_time_ms=check_result.get("response_time_ms"),
                last_check_method=check_result["check_method"],
                last_error_message=check_result.get("error_message"),
                last_checked_at=now,
                first_seen_online=now if check_result["status"] == "online" else None,
                last_seen_online=now if check_result["status"] == "online" else None,
                last_seen_offline=now if check_result["status"] == "offline" else None,
                total_checks=1,
                total_failures=1 if check_result["status"] == "offline" else 0,
                uptime_percentage=100.0 if check_result["status"] == "online" else 0.0
            )
            db.add(summary)
        else:
            # Actualizar resumen existente
            summary.last_status = check_result["status"]
            summary.last_response_time_ms = check_result.get("response_time_ms")
            summary.last_check_method = check_result["check_method"]
            summary.last_error_message = check_result.get("error_message")
            summary.last_checked_at = now
            summary.total_checks += 1
            
            if check_result["status"] == "online":
                summary.last_seen_online = now
                if not summary.first_seen_online:
                    summary.first_seen_online = now
            else:
                summary.total_failures += 1
                summary.last_seen_offline = now
            
            # Calcular porcentaje de uptime
            if summary.total_checks > 0:
                uptime_checks = summary.total_checks - summary.total_failures
                summary.uptime_percentage = (uptime_checks / summary.total_checks) * 100
    
    @staticmethod
    def get_network_statistics(db: Session) -> dict:
        """Obtiene estadísticas generales de la red"""
        total_devices = db.query(models.Device).count()
        
        summaries = db.query(models.DeviceStatusSummary).all()
        
        online_count = sum(1 for s in summaries if s.last_status == "online")
        offline_count = sum(1 for s in summaries if s.last_status == "offline")
        warning_count = sum(1 for s in summaries if s.last_status == "warning")
        
        # Calcular tiempo promedio de respuesta
        response_times = [s.last_response_time_ms for s in summaries if s.last_response_time_ms]
        avg_response = sum(response_times) / len(response_times) if response_times else None
        
        return {
            "total_devices": total_devices,
            "online_devices": online_count,
            "offline_devices": offline_count,
            "warning_devices": warning_count,
            "avg_network_response_time": avg_response,
            "last_check": max([s.last_checked_at for s in summaries]) if summaries else None
        }