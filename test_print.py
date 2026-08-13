import subprocess

# --- CONFIGURACIÓN ---
WINDOWS_IP = "192.168.1.236"  # La IP de tu PC con Windows
PRINTER_NAME = "POS-80C"        # Nombre del recurso compartido en Windows


def generar_bytes_ticket():
    """Genera la ráfaga de comandos ESC/POS."""
    b = bytearray()
    b.extend(b"\x1b\x40")                       # Reset
    b.extend(b"\x1b\x61\x01")                   # Centrar
    b.extend(b"\x1b\x21\x30")                   # Texto Grande + Negrita
    b.extend("PRUEBA DESDE PYTHON\n".encode("utf-8"))
    b.extend(b"\x1b\x21\x00")                   # Texto Normal
    b.extend("--------------------------------\n".encode("utf-8"))
    b.extend("Estado: Funciona con LPRng!\n".encode("utf-8"))
    b.extend("--------------------------------\n\n\n".encode("utf-8"))
    b.extend(b"\x1d\x56\x42\x00")               # Corte de papel
    return bytes(b)


def imprimir_vía_lpd(ip, nombre_cola, datos_bytes):
    # Formato requerido por LPRng: COLA@IP
    destino = f"{nombre_cola}@{ip}"

    try:
        # Ejecuta el comando lpr pasando los bytes por la entrada estándar (stdin)
        proceso = subprocess.run(
            ["lpr", "-P", destino],
            input=datos_bytes,
            check=True,
            capture_output=True
        )
        print("¡Ticket enviado a la impresora e impreso con éxito!")
        return True

    except subprocess.CalledProcessError as e:
        print(f"Error al enviar la impresión: {e.stderr.decode('utf-8')}")
        return False
    except FileNotFoundError:
        print("Error: El comando 'lpr' no está instalado en el sistema.")
        return False


if __name__ == "__main__":
    bytes_ticket = generar_bytes_ticket()
    imprimir_vía_lpd(WINDOWS_IP, PRINTER_NAME, bytes_ticket)