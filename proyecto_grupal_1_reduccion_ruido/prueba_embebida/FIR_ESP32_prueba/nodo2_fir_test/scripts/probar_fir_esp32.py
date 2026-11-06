from __future__ import annotations

import argparse
import csv
import json
import struct
import sys
import time
from pathlib import Path

import numpy as np
from scipy import signal

PACKAGE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_DIR))
from filtro_FIR import disenar_fir  # noqa: E402

# Si el paquete está dentro de:
# proyecto_grupal_1_reduccion_ruido/implementacion_embebida/nodo2_fir_test/
# esta ruta encuentra automáticamente la Tarea 1.
DEFAULT_TAREA1 = PACKAGE_DIR.parents[2] / "tarea1" 
BLOCK_SIZE = 1024
DEFAULT_FS = 8192


def read_exact(connection, size: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < size:
        part = connection.read(size - len(chunks))
        if not part:
            raise TimeoutError(
                f"Tiempo agotado leyendo serial: se esperaban {size} bytes, "
                f"se recibieron {len(chunks)}. Revise puerto, baudrate y firmware."
            )
        chunks.extend(part)
    return bytes(chunks)


def reset_filter(connection) -> None:
    connection.write(b"RST1")
    connection.flush()
    answer = read_exact(connection, 4)
    if answer != b"ACK1":
        raise RuntimeError(f"Respuesta inesperada al reiniciar FIR: {answer!r}")


def process_signal(connection, values: np.ndarray) -> tuple[np.ndarray, list[int]]:
    values = np.asarray(values, dtype=np.float32)
    if values.ndim != 1 or len(values) == 0:
        raise ValueError("La señal debe ser un vector 1D no vacío")
    if len(values) % BLOCK_SIZE != 0:
        raise ValueError(
            f"La señal debe tener una longitud múltiplo de {BLOCK_SIZE}; "
            f"se recibieron {len(values)} muestras"
        )

    reset_filter(connection)
    outputs = np.empty_like(values)
    timings_us: list[int] = []

    for start in range(0, len(values), BLOCK_SIZE):
        block = values[start:start + BLOCK_SIZE]
        payload = block.astype("<f4", copy=False).tobytes()
        packet = b"BLK1" + struct.pack("<H", len(block)) + payload
        connection.write(packet)
        connection.flush()

        response = read_exact(connection, 4)
        if response == b"ERR1":
            code = read_exact(connection, 1)
            raise RuntimeError(f"El firmware reportó un error: {code!r}")
        if response != b"OUT1":
            raise RuntimeError(f"Cabecera de respuesta inesperada: {response!r}")

        count = struct.unpack("<H", read_exact(connection, 2))[0]
        if count != len(block):
            raise RuntimeError(
                f"Longitud de salida inesperada: {count}; se esperaba {len(block)}"
            )
        output_bytes = read_exact(connection, count * 4)
        output_block = np.frombuffer(output_bytes, dtype="<f4").copy()
        elapsed_us = struct.unpack("<I", read_exact(connection, 4))[0]

        if not np.all(np.isfinite(output_block)):
            raise FloatingPointError("La ESP32 devolvió valores no finitos")

        outputs[start:start + count] = output_block
        timings_us.append(elapsed_us)

    return outputs, timings_us


def power(values: np.ndarray) -> float:
    return float(np.mean(np.square(np.asarray(values, dtype=np.float64))))


def db_ratio(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return float("inf")
    if numerator <= 0:
        return float("-inf")
    return float(10.0 * np.log10(numerator / denominator))


def load_case(tarea1: Path, case: int):
    case_dir = tarea1 / "pruebas" / f"caso_{case}"
    clean = np.load(case_dir / "limpia.npy").astype(np.float32)
    noise = np.load(case_dir / "ruido.npy").astype(np.float32)
    contaminated = np.load(case_dir / "contaminada.npy").astype(np.float32)

    if not (clean.shape == noise.shape == contaminated.shape):
        raise ValueError(f"Las señales del caso {case} tienen longitudes distintas")
    if len(clean) % BLOCK_SIZE != 0:
        raise ValueError("La longitud de las señales no es múltiplo de 1024")
    if not all(np.all(np.isfinite(x)) for x in (clean, noise, contaminated)):
        raise ValueError("Las señales contienen NaN o infinitos")
    return clean, noise, contaminated


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compara el FIR ejecutado en ESP32 contra la referencia Python"
    )
    parser.add_argument("--puerto", required=True, help="Puerto COM de la ESP32, por ejemplo COM6")
    parser.add_argument("--caso", type=int, choices=(1, 2, 3), default=1)
    parser.add_argument("--tarea1", type=Path, default=DEFAULT_TAREA1,
                        help="Ruta a proyecto_grupal_1_reduccion_ruido/tarea1")
    parser.add_argument("--baudrate", type=int, default=921600)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--salida", type=Path, default=PACKAGE_DIR / "resultados")
    args = parser.parse_args()

    tarea1 = args.tarea1.resolve()
    if not (tarea1 / "pruebas" / f"caso_{args.caso}").is_dir():
        parser.error(
            f"No encuentro pruebas/caso_{args.caso} dentro de {tarea1}. "
            "Use --tarea1 para indicar la ruta correcta."
        )

    try:
        import serial
    except ImportError:
        parser.error("Falta PySerial. Instale con: py -m pip install pyserial")

    clean, noise, contaminated = load_case(tarea1, args.caso)
    fs = DEFAULT_FS
    config_path = tarea1 / "metadatos" / "configuraciones.json"
    if config_path.exists():
        config = json.loads(config_path.read_text(encoding="utf-8"))
        fs = int(config.get("fs_hz", DEFAULT_FS))
    if fs != DEFAULT_FS:
        parser.error(f"El FIR fue diseñado para 8192 Hz; la configuración indica {fs} Hz")

    b = np.asarray(disenar_fir(fs), dtype=np.float64)
    print(f"Caso {args.caso}; fs={fs} Hz; muestras={len(clean)}; bloques={len(clean)//BLOCK_SIZE}")
    print(f"Conectando con {args.puerto} a {args.baudrate} baudios...")
    print("Cierre el Monitor Serial del Arduino IDE antes de ejecutar esta prueba.")

    try:
        with serial.Serial(
            args.puerto,
            baudrate=args.baudrate,
            timeout=args.timeout,
            write_timeout=args.timeout,
        ) as connection:
            # Abrir el puerto suele reiniciar el ESP32.
            time.sleep(2.0)
            connection.reset_input_buffer()
            connection.reset_output_buffer()

            print("Procesando señal contaminada en la ESP32...")
            out_mixed, block_times = process_signal(connection, contaminated)
            print("Procesando referencia limpia en la ESP32...")
            out_clean, _ = process_signal(connection, clean)
            print("Procesando ruido aislado en la ESP32...")
            out_noise, _ = process_signal(connection, noise)
    except (OSError, TimeoutError, RuntimeError) as exc:
        print(f"ERROR de comunicación: {exc}")
        return 1

    # Referencia matemática en PC con las mismas muestras float32 enviadas.
    py_mixed = signal.lfilter(b, [1.0], contaminated.astype(np.float64))
    py_clean = signal.lfilter(b, [1.0], clean.astype(np.float64))
    py_noise = signal.lfilter(b, [1.0], noise.astype(np.float64))

    max_error = float(np.max(np.abs(out_mixed.astype(np.float64) - py_mixed)))
    rmse_equivalence = float(np.sqrt(np.mean(np.square(out_mixed.astype(np.float64) - py_mixed))))

    # Misma alineación y descarte de transitorios que probar_FIR.py.
    delay = (len(b) - 1) // 2
    margin = len(b) - 1
    start = margin
    end = len(clean) - delay - margin
    if end <= start:
        raise ValueError("La señal es demasiado corta para evaluar el FIR")

    reference = clean[start:end].astype(np.float64)
    noise_reference = noise[start:end].astype(np.float64)
    mixed_aligned = out_mixed[start + delay:end + delay].astype(np.float64)
    clean_aligned = out_clean[start + delay:end + delay].astype(np.float64)
    noise_aligned = out_noise[start + delay:end + delay].astype(np.float64)

    error = reference - mixed_aligned
    mse = power(error)
    snr_input = db_ratio(power(reference), power(noise_reference))
    snr_output = db_ratio(power(reference), power(error))
    delta_snr = snr_output - snr_input
    energy_pct = 100.0 * power(clean_aligned) / power(reference)
    attenuation_db = db_ratio(power(noise_reference), power(noise_aligned))

    deadline_us = 1_000_000.0 * BLOCK_SIZE / fs
    mean_us = float(np.mean(block_times))
    max_us = int(max(block_times))
    equivalent = max_error <= 5e-5
    within_deadline = max_us < deadline_us

    args.salida.mkdir(parents=True, exist_ok=True)
    np.save(args.salida / f"caso_{args.caso}_salida_esp32.npy", out_mixed)
    with (args.salida / f"caso_{args.caso}_tiempos_bloque.csv").open(
        "w", newline="", encoding="utf-8"
    ) as file:
        writer = csv.writer(file)
        writer.writerow(["bloque", "tiempo_fir_us", "presupuesto_bloque_us"])
        for index, elapsed in enumerate(block_times):
            writer.writerow([index, elapsed, deadline_us])

    summary = {
        "caso": args.caso,
        "fs_hz": fs,
        "N_bloque": BLOCK_SIZE,
        "retardo_muestras": delay,
        "retardo_ms": 1000.0 * delay / fs,
        "MSE": mse,
        "SNR_entrada_dB": snr_input,
        "SNR_salida_dB": snr_output,
        "Delta_SNR_dB": delta_snr,
        "Energia_util_pct": energy_pct,
        "Atenuacion_ruido_dB": attenuation_db,
        "max_error_ESP32_vs_Python": max_error,
        "RMSE_ESP32_vs_Python": rmse_equivalence,
        "tiempo_medio_FIR_bloque_us": mean_us,
        "tiempo_maximo_FIR_bloque_us": max_us,
        "presupuesto_bloque_us": deadline_us,
        "equivalencia_numerica_atol_5e-5": equivalent,
        "FIR_calculo_menor_125ms": within_deadline,
        "nota": "Tiempo medido solo para el cálculo FIR; excluye ADC, DAC/PWM y comunicación serial."
    }

    summary_path = args.salida / f"caso_{args.caso}_resumen_esp32.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    csv_path = args.salida / f"caso_{args.caso}_metricas_esp32.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(summary.keys()))
        writer.writeheader()
        writer.writerow(summary)

    print("\nRESULTADOS DE LA ESP32")
    print("----------------------")
    for key in (
        "MSE", "SNR_entrada_dB", "SNR_salida_dB", "Delta_SNR_dB",
        "Energia_util_pct", "Atenuacion_ruido_dB",
    ):
        print(f"{key}: {summary[key]:.6f}")
    print(f"Máximo error ESP32 vs Python: {max_error:.8g}")
    print(f"RMSE ESP32 vs Python: {rmse_equivalence:.8g}")
    print(f"Tiempo FIR medio por bloque: {mean_us:.2f} us")
    print(f"Tiempo FIR máximo por bloque: {max_us} us")
    print(f"Presupuesto de un bloque de 1024 muestras: {deadline_us:.0f} us")
    print(f"Equivalencia numérica (tolerancia 5e-5): {'OK' if equivalent else 'REVISAR'}")
    print(f"Cálculo FIR menor que 125 ms: {'OK' if within_deadline else 'REVISAR'}")
    print(f"Resultados guardados en: {args.salida.resolve()}")

    return 0 if equivalent and within_deadline else 2


if __name__ == "__main__":
    raise SystemExit(main())
