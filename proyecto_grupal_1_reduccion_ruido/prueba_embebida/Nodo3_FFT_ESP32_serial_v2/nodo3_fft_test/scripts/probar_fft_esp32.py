import argparse
import os
import time
import csv
from datetime import datetime

import numpy as np
import serial


def read_line(ser, timeout_s=30):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        raw = ser.readline()
        if raw:
            return raw.decode("ascii", errors="replace").strip()
    raise TimeoutError("No se recibió respuesta de la ESP32.")


def wait_for_board(ser, timeout_s=10):
    """Comprueba que el firmware responde a PING sin depender del READY inicial."""
    ser.reset_input_buffer()
    ser.write(b"PING\n")
    ser.flush()

    previous_timeout = ser.timeout
    ser.timeout = 1
    deadline = time.monotonic() + timeout_s
    try:
        while time.monotonic() < deadline:
            raw = ser.readline()
            if not raw:
                continue
            line = raw.decode("ascii", errors="replace").strip()
            if line == "PONG,NODE3_FFT_OLA":
                return line
            if line.startswith("ERR,"):
                raise RuntimeError(f"La ESP32 respondió con un error: {line}")
    finally:
        ser.timeout = previous_timeout

    raise TimeoutError(
        "No se recibió PONG,NODE3_FFT_OLA. Comprueba el puerto COM, el firmware "
        "cargado y que el Monitor Serial esté cerrado."
    )


def send_payload_in_chunks(ser, payload, chunk_size=128, pause_s=0.005):
    """Transmite el bloque por fragmentos para evitar ráfagas grandes en el UART."""
    for offset in range(0, len(payload), chunk_size):
        ser.write(payload[offset:offset + chunk_size])
        if pause_s > 0:
            time.sleep(pause_s)
    ser.flush()


def process(ser, operation, data, threshold):
    x = np.ascontiguousarray(np.asarray(data, dtype="<f4").reshape(-1))
    command = f"{operation},{len(x)},1024,{threshold:.6f}\n".encode("ascii")
    ser.write(command)
    ser.flush()

    # La ESP32 confirma que ya terminó de analizar el comando y está leyendo.
    ready = read_line(ser, 15)
    if ready.startswith("ERR,"):
        raise RuntimeError(ready)
    expected_ready = f"READY_DATA,{len(x)}"
    if ready != expected_ready:
        raise RuntimeError(
            f"Respuesta inesperada antes de enviar datos: {ready!r}; "
            f"se esperaba {expected_ready!r}. Vuelve a cargar el sketch v2."
        )

    payload = x.tobytes(order="C")
    send_payload_in_chunks(ser, payload)

    line = read_line(ser, 60)
    if line.startswith("ERR,"):
        raise RuntimeError(line)
    fields = line.split(",")
    if len(fields) != 5 or fields[0] != "BEGIN":
        raise RuntimeError(f"Respuesta inesperada: {line}")

    n, total_us, max_frame_us, frame_count = map(int, fields[1:])
    if n != len(x):
        raise RuntimeError("La cantidad de muestras devuelta no coincide.")

    raw = bytearray()
    expected_bytes = n * 4
    while len(raw) < expected_bytes:
        part = ser.read(expected_bytes - len(raw))
        if not part:
            raise TimeoutError(
                f"Respuesta binaria incompleta: {len(raw)} de {expected_bytes} bytes."
            )
        raw.extend(part)

    end_line = read_line(ser, 30)
    if end_line != "END":
        raise RuntimeError(f"Se esperaba END y llegó: {end_line}")

    y = np.frombuffer(raw, dtype="<f4").copy()
    return y, total_us, max_frame_us, frame_count

def potencia_media(signal_data):
    x = np.asarray(signal_data, dtype=np.float64).reshape(-1)
    return float(np.mean(x ** 2))


def calcular_db(numerador, denominador):
    if denominador <= 0:
        return float("inf") if numerador > 0 else float("nan")

    if numerador <= 0:
        return float("-inf")

    return float(10 * np.log10(numerador / denominador))


def calcular_metricas(clean, noise, clean_out, noise_out):

    clean = np.asarray(clean, dtype=np.float64).reshape(-1)
    noise = np.asarray(noise, dtype=np.float64).reshape(-1)
    clean_out = np.asarray(clean_out, dtype=np.float64).reshape(-1)
    noise_out = np.asarray(noise_out, dtype=np.float64).reshape(-1)

    if not (len(clean) == len(noise) == len(clean_out) == len(noise_out)):
        raise ValueError("Las señales no tienen la misma cantidad de muestras.")

    # Potencias de las señales originales
    potencia_clean = potencia_media(clean)
    potencia_noise = potencia_media(noise)

    # Potencias después del filtrado
    potencia_clean_out = potencia_media(clean_out)
    potencia_noise_out = potencia_media(noise_out)

    # Error cuadrático medio
    mse = float(np.mean((clean - clean_out) ** 2))

    # Relación señal a ruido de entrada
    snr_entrada = calcular_db(potencia_clean, potencia_noise)

    # Relación señal a ruido de salida
    snr_salida = calcular_db(potencia_clean_out, potencia_noise_out)

    # Mejora de la relación señal a ruido
    delta_snr = snr_salida - snr_entrada

    # Porcentaje de energía útil conservada
    energia_conservada = (
        100 * potencia_clean_out / potencia_clean
        if potencia_clean > 0 else float("nan")
    )

    # Atenuación del ruido
    atenuacion_ruido = calcular_db(
        potencia_noise, potencia_noise_out
    )

    return {
        "MSE": mse,
        "SNR_entrada_dB": snr_entrada,
        "SNR_salida_dB": snr_salida,
        "Delta_SNR_dB": delta_snr,
        "Energia_util_conservada_pct": energia_conservada,
        "Atenuacion_ruido_dB": atenuacion_ruido
    }


def guardar_metricas_csv(path, row):

    existe = os.path.isfile(path) and os.path.getsize(path) > 0

    with open(path, "a", newline="", encoding="utf-8") as archivo:
        writer = csv.DictWriter(
            archivo,
            fieldnames=list(row.keys())
        )

        if not existe:
            writer.writeheader()

        writer.writerow(row)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True, help="Ejemplo: COM8")
    parser.add_argument("--baud", type=int, default=921600)
    parser.add_argument("--tarea1", required=True, help="Ruta a la carpeta tarea1")
    parser.add_argument("--threshold", type=float, default=0.10)
    parser.add_argument(
        "--case", choices=["caso_1", "caso_2", "caso_3", "all"], default="all"
    )
    args = parser.parse_args()

    cases = ["caso_1", "caso_2", "caso_3"] if args.case == "all" else [args.case]
    ser = serial.Serial(args.port, args.baud, timeout=30, write_timeout=30)
    time.sleep(2)  # Permite que la ESP32 termine el reinicio al abrir el puerto.

    try:
        print("Placa:", wait_for_board(ser, 10))
        for case in cases:
            folder = os.path.join(args.tarea1, "pruebas", case)
            contaminated = np.load(os.path.join(folder, "contaminada.npy"))
            clean = np.load(os.path.join(folder, "limpia.npy"))
            noise = np.load(os.path.join(folder, "ruido.npy"))

            _, t_mix, max_mix, frames = process(
                ser, "LEARN", contaminated, args.threshold
            )
            clean_out, t_clean, max_clean, _ = process(
                ser, "REPLAY", clean, args.threshold
            )
            noise_out, t_noise, max_noise, _ = process(
                ser, "REPLAY", noise, args.threshold
            )

            print(f"\n{case}: {frames} ventanas")
            print(f"  LEARN mezcla: total={t_mix} us, max ventana={max_mix} us")
            print(f"  REPLAY limpia: total={t_clean} us, max ventana={max_clean} us")
            print(f"  REPLAY ruido: total={t_noise} us, max ventana={max_noise} us")
            # Guardar señales filtradas
            np.save(os.path.join(folder, "limpia_fft_esp32.npy"), clean_out)
            np.save(os.path.join(folder, "ruido_fft_esp32.npy"), noise_out)

            # Calcular métricas de calidad
            metricas = calcular_metricas(
                clean,
                noise,
                clean_out,
                noise_out
            )

            print("\n  MÉTRICAS DE CALIDAD DEL FILTRADO")

            for nombre, valor in metricas.items():
                print(f"  {nombre}: {valor:.6f}")

            # Guardar resultados para el informe
            fila = {
                "Fecha": datetime.now().isoformat(timespec="seconds"),
                "Caso": case,
                **metricas,
                "LEARN_total_us": t_mix,
                "REPLAY_limpia_total_us": t_clean,
                "REPLAY_ruido_total_us": t_noise,
                "LEARN_max_ventana_us": max_mix,
                "REPLAY_max_ventana_us": max(max_clean, max_noise),
                "Cantidad_ventanas": frames
            }

            ruta_csv = os.path.join(
                args.tarea1,
                "resultados_fft_esp32.csv"
            )

            guardar_metricas_csv(ruta_csv, fila)

            print(f"\n  Resultados guardados en: {ruta_csv}")
    finally:
        ser.close()


if __name__ == "__main__":
    main()
