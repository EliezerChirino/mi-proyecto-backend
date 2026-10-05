"""
Verificación del estado de los dispositivos.

Cascada: SNMP → ping (ICMP) → puertos TCP.
Si un método falla se prueba el siguiente; el equipo solo se declara
"offline" cuando fallan los tres.

Todo es asíncrono: el monitor verifica muchos equipos en paralelo
sin bloquear FastAPI.

Prueba rápida sin base de datos (desde la carpeta backend):
    python -m app.servicios.monitor_red 192.168.12.1 192.168.12.111
"""
import asyncio
import platform
import re
import subprocess
import sys
import time

from pysnmp.hlapi.v3arch.asyncio import (
    CommunityData,
    ContextData,
    ObjectIdentity,
    ObjectType,
    SnmpEngine,
    UdpTransportTarget,
    get_cmd,
)

# ─── Configuración ───────────────────────────────────────────────

ES_WINDOWS = platform.system() == "Windows"

SNMP_COMUNIDAD = "public"
SNMP_OID_UPTIME = "1.3.6.1.2.1.1.3.0"   # tiempo encendido del equipo
SNMP_TIMEOUT_S = 2

PING_TIMEOUT_S = 2

TCP_TIMEOUT_S = 1.5
# Puertos habituales en una red de oficina, del más al menos probable
TCP_PUERTOS = [445, 3389, 80, 443, 22, 9100, 135, 8080]

# Máximo de equipos verificándose a la vez
MAX_EN_PARALELO = 50

# Mostrar en consola cada paso de la cascada
MOSTRAR_PASOS = True

_snmp_engine = None
_semaforo = None


# ─── Utilidades ──────────────────────────────────────────────────




def ms_desde(inicio: float) -> float:
    return round((time.perf_counter() - inicio) * 1000, 1)


def obtener_snmp_engine() -> SnmpEngine:
    """Un solo motor SNMP para toda la app (crearlo es costoso)."""
    global _snmp_engine
    if _snmp_engine is None:
        _snmp_engine = SnmpEngine()
    return _snmp_engine


def obtener_semaforo() -> asyncio.Semaphore:
    """Limita cuántos equipos se verifican en paralelo."""
    global _semaforo
    if _semaforo is None:
        _semaforo = asyncio.Semaphore(MAX_EN_PARALELO)
    return _semaforo


# ─── Método 1: SNMP ──────────────────────────────────────────────

async def consultar_snmp(ip: str) -> dict:
    inicio = time.perf_counter()
    try:
        destino = await UdpTransportTarget.create(
            (ip, 161), timeout=SNMP_TIMEOUT_S, retries=0
        )
        error_ind, error_status, _, var_binds = await get_cmd(
            obtener_snmp_engine(),
            CommunityData(SNMP_COMUNIDAD, mpModel=1),   # SNMP v2c
            destino,
            ContextData(),
            ObjectType(ObjectIdentity(SNMP_OID_UPTIME)),
        )
    except Exception as e:
        return {"ok": False, "error": f"SNMP: {e}"}

    if error_ind:
        return {"ok": False, "error": f"SNMP: {error_ind}"}
    if error_status:
        return {"ok": False, "error": f"SNMP: {error_status.prettyPrint()}"}

    datos = {str(nombre): str(valor) for nombre, valor in var_binds}
    return {"ok": True, "metodo": "snmp", "ms": ms_desde(inicio), "snmp_data": str(datos)}


# ─── Método 2: ping (ICMP) ───────────────────────────────────────

def _ping_bloqueante(ip: str) -> dict:
    """
    Ejecuta el ping del sistema. Es bloqueante: se llama desde un hilo
    aparte (asyncio.to_thread) para no congelar el servidor.
    """
    if ES_WINDOWS:
        comando = ["ping", "-n", "1", "-w", str(PING_TIMEOUT_S * 1000), ip]
    else:
        comando = ["ping", "-c", "1", "-W", str(PING_TIMEOUT_S), ip]

    inicio = time.perf_counter()
    try:
        resultado = subprocess.run(
            comando,
            capture_output=True,
            text=True,
            errors="ignore",
            timeout=PING_TIMEOUT_S + 2,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "ICMP: tiempo agotado"}
    except Exception as e:
        return {"ok": False, "error": f"ICMP: {e}"}

    salida = resultado.stdout
    # "TTL=" solo aparece si respondió el equipo (no en "Host de destino inaccesible")
    if "TTL=" not in salida.upper():
        return {"ok": False, "error": "ICMP: sin respuesta"}

    # Windows: "tiempo=3ms" / "tiempo<1m"; Linux: "time=3.2 ms"
    coincidencia = re.search(r"(?:tiempo|time)\s*[=<]\s*(\d+(?:[.,]\d+)?)", salida, re.IGNORECASE)
    if coincidencia:
        ms = float(coincidencia.group(1).replace(",", "."))
    else:
        ms = ms_desde(inicio)
    return {"ok": True, "metodo": "icmp", "ms": ms}


async def hacer_ping(ip: str) -> dict:
    return await asyncio.to_thread(_ping_bloqueante, ip)


# ─── Método 3: puertos TCP ───────────────────────────────────────

async def _probar_puerto(ip: str, puerto: int):
    """
    Devuelve (puerto, ms, detalle) si el equipo respondió, o None.
    Conexión aceptada = puerto abierto.
    Conexión rechazada (RST) = puerto cerrado, PERO el equipo está vivo.
    Sin respuesta = firewall o equipo apagado.
    """
    inicio = time.perf_counter()
    try:
        _, escritor = await asyncio.wait_for(
            asyncio.open_connection(ip, puerto), timeout=TCP_TIMEOUT_S
        )
    except ConnectionRefusedError:
        return (puerto, ms_desde(inicio), "cerrado (RST)")
    except (OSError, asyncio.TimeoutError):
        return None

    ms = ms_desde(inicio)
    escritor.close()
    try:
        await escritor.wait_closed()
    except Exception:
        pass
    return (puerto, ms, "abierto")


async def probar_tcp(ip: str) -> dict:
    # Todos los puertos a la vez: tarda lo mismo que uno solo
    respuestas = await asyncio.gather(*(_probar_puerto(ip, p) for p in TCP_PUERTOS))
    validas = [r for r in respuestas if r is not None]
    if not validas:
        return {"ok": False, "error": "TCP: ningún puerto respondió"}

    # Preferir un puerto abierto; si no, cualquiera que haya rechazado
    abiertos = [r for r in validas if r[2] == "abierto"]
    puerto, ms, detalle = min(abiertos or validas, key=lambda r: r[1])
    return {
        "ok": True,
        "metodo": f"tcp:{puerto}",
        "ms": ms,
        "detalle": f"puerto {puerto} {detalle}",
    }


# ─── Cascada ─────────────────────────────────────────────────────

# Orden de la cascada: (etiqueta para la consola, función que verifica)
METODOS = [
    ("SNMP", consultar_snmp),
    ("ICMP", hacer_ping),
    ("TCP", probar_tcp),
]

ANCHO_CONSOLA = 64


def _resultado(ip, status, metodo=None, ms=None, error=None, snmp_data=None) -> dict:
    """Formato que espera StatusService.save_device_status."""
    return {
        "ip": ip,
        "status": status,
        "check_method": metodo,
        "response_time_ms": ms,
        "error_message": error,
        "snmp_data": snmp_data,
    }


def _describir_paso(etiqueta: str, r: dict) -> str:
    """Una línea por método: 'ICMP  ✓  38.0 ms' o 'SNMP  ✗  sin respuesta'."""
    if r["ok"]:
        extra = f" · {r['detalle']}" if r.get("detalle") else ""
        return f"{etiqueta:<5} ✓  {r['ms']} ms{extra}"
    motivo = r["error"].split(": ", 1)[-1]   # quita el prefijo "SNMP: " repetido
    return f"{etiqueta:<5} ✗  {motivo}"


def _imprimir_bloque(titulo: str, pasos: list, cierre: str) -> None:
    """
    Imprime todo el recorrido de un equipo de una sola vez.
    Como los equipos se verifican en paralelo, imprimir línea por línea
    mezclaría los mensajes de unos con otros.
    """
    if not MOSTRAR_PASOS:
        return
    cabecera = f"┌─ {titulo} "
    lineas = [cabecera + "─" * max(0, ANCHO_CONSOLA - len(cabecera))]
    lineas += [f"│  {paso}" for paso in pasos]
    lineas.append(f"└─ {cierre}")
    print("\n".join(lineas) + "\n", flush=True)


async def verificar_dispositivo(ip: str, nombre: str = None) -> dict:
    """Prueba SNMP → ping → TCP y se detiene en el primero que responda."""
    async with obtener_semaforo():
        pasos = []
        errores = []

        for etiqueta, verificar in METODOS:
            r = await verificar(ip)
            pasos.append(_describir_paso(etiqueta, r))
            if r["ok"]:
                resultado = _resultado(ip, "online", r["metodo"], r["ms"], snmp_data=r.get("snmp_data"))
                cierre = f"EN LÍNEA · {r['metodo']} · {r['ms']} ms"
                break
            errores.append(r["error"])
        else:
            # El "else" de un for se ejecuta solo si el bucle terminó SIN "break":
            # es decir, ningún método respondió.
            resultado = _resultado(ip, "offline", error="; ".join(errores))
            cierre = "FUERA DE LÍNEA"

    titulo = f"{nombre} · {ip}" if nombre else ip
    _imprimir_bloque(titulo, pasos, cierre)
    return resultado
# ─── Prueba manual desde la terminal ─────────────────────────────

async def _prueba_manual(ips):
    inicio = time.perf_counter()
    resultados = await asyncio.gather(*(verificar_dispositivo(ip) for ip in ips))
    print("\nResumen:")
    for r in resultados:
        ms = f"{r['response_time_ms']} ms" if r["response_time_ms"] is not None else "—"
        print(f"   {r['ip']:<16} {r['status'].upper():<8} {r['check_method'] or '-':<9} {ms}")
    print(f"\nTotal: {ms_desde(inicio)} ms para {len(ips)} equipo(s)")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python -m app.servicios.monitor_red <ip> [<ip> ...]")
        sys.exit(1)
    asyncio.run(_prueba_manual(sys.argv[1:]))