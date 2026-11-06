#!/usr/bin/env python3
"""Receptor de prueba para paquetes binarios N1B2 transmitidos por UART2."""
from __future__ import annotations

import argparse
import csv
import json
import struct
import time
import zlib
from pathlib import Path

import numpy as np

MAGIC = b"N1B2"
HEADER_FORMAT = "<4sBBIIIHHI"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
VERSION = 1


def read_exact(port, count: int) -> bytes:
    data = bytearray()
    deadline = time.monotonic() + max(3.0, count * 10 / max(getattr(port, "baudrate", 921600), 1) + 2.0)
    while len(data) < count and time.monotonic() < deadline:
        piece = port.read(count - len(data))
        if piece:
            data.extend(piece)
    if len(data) != count:
        raise TimeoutError(f"Se esperaban {count} bytes; llegaron {len(data)}.")
    return bytes(data)


def seek_magic(port) -> bytes:
    window = bytearray()
    while True:
        byte = port.read(1)
        if not byte:
            continue
        window.extend(byte)
        if len(window) > len(MAGIC):
            del window[0]
        if bytes(window) == MAGIC:
            return MAGIC


def receive_packet(port):
    magic = seek_magic(port)
    rest = read_exact(port, HEADER_SIZE - len(MAGIC))
    header = magic + rest
    (magic, version, flags, seq, fs_adc_cfg, fs_out_nominal,
     n_raw, n_out, dma_read_us) = struct.unpack(HEADER_FORMAT, header)
    if version != VERSION:
        raise ValueError(f"Version N1B2 no soportada: {version}")
    if not (1 <= n_out <= 8192 and 1 <= n_raw <= 32768):
        raise ValueError(f"Longitudes inesperadas: raw={n_raw}, salida={n_out}")

    payload = read_exact(port, n_out * 4)
    crc_bytes = read_exact(port, 4)
    crc_received = struct.unpack("<I", crc_bytes)[0]
    crc_calculated = zlib.crc32(header + payload) & 0xFFFFFFFF
    if crc_received != crc_calculated:
        raise ValueError(
            f"CRC incorrecto seq={seq}: recibido=0x{crc_received:08X}, "
            f"calculado=0x{crc_calculated:08X}"
        )
    samples = np.frombuffer(payload, dtype="<f4").astype(np.float32, copy=True)
    if not np.all(np.isfinite(samples)):
        raise ValueError(f"Muestras no finitas en bloque {seq}")
    return {
        "sequence": seq,
        "flags": flags,
        "fs_adc_configured_hz": fs_adc_cfg,
        "fs_output_nominal_hz": fs_out_nominal,
        "raw_samples": n_raw,
        "output_samples": n_out,
        "dma_read_elapsed_us": dma_read_us,
        "crc32": f"0x{crc_received:08X}",
        "samples": samples,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--puerto", required=True, help="COM del adaptador USB-UART")
    parser.add_argument("--baudrate", type=int, default=921600)
    parser.add_argument("--bloques", type=int, default=5)
    parser.add_argument("--salida", type=Path, default=Path("resultados_nodo1_uart"))
    args = parser.parse_args()
    if args.bloques <= 0:
        parser.error("--bloques debe ser positivo")

    import serial

    args.salida.mkdir(parents=True, exist_ok=True)
    captured = []
    with serial.Serial(args.puerto, args.baudrate, timeout=0.25) as port:
        port.reset_input_buffer()
        print(f"Escuchando {args.puerto} a {args.baudrate} baudios...")
        while len(captured) < args.bloques:
            try:
                packet = receive_packet(port)
            except (ValueError, TimeoutError) as exc:
                print(f"Paquete descartado: {exc}")
                continue
            samples = packet.pop("samples")
            packet["adc_min_norm"] = float(np.min(samples))
            packet["adc_max_norm"] = float(np.max(samples))
            packet["adc_mean_norm"] = float(np.mean(samples))
            packet["adc_rms_norm"] = float(np.sqrt(np.mean(samples.astype(np.float64) ** 2)))
            packet["crc_ok"] = True
            captured.append((packet, samples))
            print(
                f"Bloque {packet['sequence']}: CRC=OK, "
                f"FS ADC configurada={packet['fs_adc_configured_hz']}, "
                f"FS salida nominal={packet['fs_output_nominal_hz']}, "
                f"rango={packet['adc_min_norm']:.5f}..{packet['adc_max_norm']:.5f}, "
                f"flags=0x{packet['flags']:02X}"
            )

    # CSV largo y JSON resumen. El tiempo de la columna procede de FS nominal.
    csv_path = args.salida / "muestras_nodo1_uart.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["bloque", "muestra", "tiempo_nominal_s", "valor_normalizado"])
        for packet, samples in captured:
            fs = packet["fs_output_nominal_hz"]
            for i, value in enumerate(samples):
                writer.writerow([packet["sequence"], i, i / fs, float(value)])

    summary = {
        "port": args.puerto,
        "baudrate": args.baudrate,
        "blocks_received": len(captured),
        "all_crc_valid": all(p["crc_ok"] for p, _ in captured),
        "frequency_note": "fs_output_nominal_hz solo es nominal hasta calibrar la tasa ADC real.",
        "blocks": [p for p, _ in captured],
    }
    json_path = args.salida / "resumen_nodo1_uart.json"
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nGuardado: {csv_path}")
    print(f"Guardado: {json_path}")


if __name__ == "__main__":
    main()
