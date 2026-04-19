import time
import subprocess
from pysnmp.hlapi import *


class NetworkMonitor:
    """Servicio para verificar conectividad de dispositivos"""
    
    @staticmethod
    def consulta_snmp(host: str, community: str = "public", oid: str = "1.3.6.1.2.1.1.3.0") -> dict:
        """
        Realiza una consulta SNMP a un dispositivo
        
        Args:
            host: Dirección IP del dispositivo
            community: Comunidad SNMP (por defecto 'public')
            oid: OID a consultar (por defecto: uptime)
            
        Returns:
            dict: {
                "success": bool,
                "data": dict (si success=True),
                "error": str (si success=False),
                "response_time_ms": float
            }
        """
        start_time = time.time()
        
        try:
            iterator = getCmd(
                SnmpEngine(),
                CommunityData(community, mpModel=1),  # SNMPv2c
                UdpTransportTarget((host, 161), timeout=5, retries=1),
                ContextData(),
                ObjectType(ObjectIdentity(oid))
            )
            
            errorIndication, errorStatus, errorIndex, varBinds = next(iterator)
            response_time = (time.time() - start_time) * 1000  # ms
            
            if errorIndication:
                return {
                    "success": False,
                    "error": str(errorIndication),
                    "response_time_ms": response_time
                }
            elif errorStatus:
                return {
                    "success": False,
                    "error": errorStatus.prettyPrint(),
                    "response_time_ms": response_time
                }
            else:
                result = {}
                for varBind in varBinds:
                    oid_str = str(varBind[0])
                    result[oid_str] = str(varBind[1])
                return {
                    "success": True,
                    "data": result,
                    "response_time_ms": response_time
                }
                
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            return {
                "success": False,
                "error": f"Excepción SNMP: {str(e)}",
                "response_time_ms": response_time
            }
    
    @staticmethod
    def verificar_icmp(ip: str) -> dict:
        """
        Verifica la conectividad con un dispositivo usando ping (ICMP)
        
        Args:
            ip: Dirección IP del dispositivo
            
        Returns:
            dict: {
                "success": bool,
                "error": str (opcional),
                "response_time_ms": float
            }
        """
        start_time = time.time()
        
        try:
            # Windows usa -n, Linux/Mac usa -c
            ping_cmd = ["ping", "-n", "4", ip] if subprocess.os.name == "nt" else ["ping", "-c", "4", ip]
            
            ping_result = subprocess.run(
                ping_cmd,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            response_time = (time.time() - start_time) * 1000  # ms
            
            # Verificar si hubo respuesta
            if "TTL=" in ping_result.stdout or "ttl=" in ping_result.stdout:
                return {
                    "success": True,
                    "response_time_ms": response_time
                }
            else:
                return {
                    "success": False,
                    "error": "Sin respuesta ICMP",
                    "response_time_ms": response_time
                }
                
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": "Timeout en ping",
                "response_time_ms": 10000
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Error en ping: {str(e)}",
                "response_time_ms": 0
            }
    
    @staticmethod
    def verificar_dispositivo(ip: str, check_method: str = "both") -> dict:
        """
        Verifica el estado de un dispositivo usando SNMP y/o ICMP
        
        Args:
            ip: Dirección IP del dispositivo
            check_method: "snmp", "icmp", o "both"
            
        Returns:
            dict: {
                "ip": str,
                "status": "online" | "offline",
                "response_time_ms": float,
                "check_method": str,
                "error_message": str (opcional),
                "snmp_data": str (opcional)
            }
        """
        result = {
            "ip": ip,
            "status": "offline",
            "response_time_ms": None,
            "check_method": check_method,
            "error_message": None,
            "snmp_data": None
        }
        
        # Intentar SNMP primero si está habilitado
        if check_method in ["snmp", "both"]:
            snmp_result = NetworkMonitor.consulta_snmp(ip)
            
            if snmp_result["success"]:
                result["status"] = "online"
                result["response_time_ms"] = snmp_result["response_time_ms"]
                result["check_method"] = "snmp"
                result["snmp_data"] = str(snmp_result.get("data", {}))
                return result
            else:
                result["error_message"] = snmp_result["error"]
        
        # Si SNMP falló o no se usó, intentar ICMP
        if check_method in ["icmp", "both"]:
            icmp_result = NetworkMonitor.verificar_icmp(ip)
            
            if icmp_result["success"]:
                result["status"] = "online"
                result["response_time_ms"] = icmp_result["response_time_ms"]
                result["check_method"] = "icmp"
                return result
            else:
                if not result["error_message"]:
                    result["error_message"] = icmp_result["error"]
                else:
                    result["error_message"] += f"; {icmp_result['error']}"
        
        return result