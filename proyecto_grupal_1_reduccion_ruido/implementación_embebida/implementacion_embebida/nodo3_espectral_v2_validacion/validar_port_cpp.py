#!/usr/bin/env python3
"""Compara el port C++ streaming del Nodo 3 con la referencia Python sin look-back."""
from __future__ import annotations
import argparse
import csv
import subprocess
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
DEFAULT_DATA = HERE / "datos_prueba"


def compile_cpp(compiler: str, output: Path) -> None:
    source = HERE / "prueba_fft_v2.cpp"
    header = HERE / "fft_ola_v2_stream.h"
    subprocess.run([compiler, "-std=c++11", "-O2", str(source), "-o", str(output)], check=True)
    if not header.exists():
        raise FileNotFoundError(header)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--datos", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--compiler", default="g++")
    args = parser.parse_args()
    from filtrado_espectral_v2_nolookback import reducir_espectral_v2

    executable = HERE / ("prueba_fft_v2.exe" if __import__("os").name == "nt" else "prueba_fft_v2")
    compile_cpp(args.compiler, executable)
    input_path, output_path = HERE / "entrada.bin", HERE / "salida_cpp.bin"
    rows = []
    for case in range(1, 6):
        for repetition in range(1, 4):
            path = args.datos / f"caso_{case}_rep_{repetition}_senales.npz"
            arrays = np.load(path)
            mixed = arrays["entrada_nodo1"].astype(np.float32)
            clean = arrays["limpia_nodo1"].astype(np.float64)
            mixed.tofile(input_path)
            subprocess.run([str(executable), str(input_path), str(output_path)],
                           check=True, stdout=subprocess.DEVNULL)
            cpp = np.fromfile(output_path, dtype=np.float32).astype(np.float64)
            python_ref = reducir_espectral_v2(mixed.astype(np.float64))
            if cpp.shape != python_ref.shape:
                raise AssertionError(f"Longitud distinta caso {case}, repeticion {repetition}")
            diff = cpp - python_ref
            snr_in = 10 * np.log10(np.sum(clean ** 2) / np.sum((clean - mixed) ** 2))
            snr_out = 10 * np.log10(np.sum(clean ** 2) / np.sum((clean - cpp) ** 2))
            rows.append({
                "caso": case, "repeticion": repetition,
                "error_max_abs": float(np.max(np.abs(diff))),
                "error_rms": float(np.sqrt(np.mean(diff ** 2))),
                "mejora_snr_cpp_db": float(snr_out - snr_in),
            })
    csv_path = HERE / "validacion_cpp_vs_python.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    for case in range(1, 6):
        group = [r for r in rows if r["caso"] == case]
        print(f"Caso {case}: error maximo={max(r['error_max_abs'] for r in group):.3e}; "
              f"ΔSNR C++ media={np.mean([r['mejora_snr_cpp_db'] for r in group]):+.3f} dB")
    max_error = max(r["error_max_abs"] for r in rows)
    print(f"\n15/15 comparaciones completadas. Error absoluto maximo: {max_error:.3e}")
    print(f"CSV: {csv_path}")
    if max_error > 1e-4:
        raise SystemExit("FALLO: port C++ fuera de tolerancia 1e-4")


if __name__ == "__main__":
    main()
