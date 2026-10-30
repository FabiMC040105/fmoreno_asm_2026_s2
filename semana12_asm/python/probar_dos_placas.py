"""CE1110 Semana 12: pruebas con DOS ESP32 y un enlace analogico.

    python python/probar_dos_placas.py --emisor COM6 --receptor COM7 --modo 4
    python python/probar_dos_placas.py --emisor COM6 --receptor COM7 --todos
    python python/probar_dos_placas.py --simular --todos

El programa controla por USB ambos ESP32, pero la SENAL de prueba cruza
fisicamente desde la salida DAC/PWM del emisor hasta el ADC del receptor.
La FFT y validacion se efectuan en el PC. --simular NO es evidencia fisica.
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path
from typing import Any

from validar_fft_receptor import (
    EXPECTED, FS, N, analizar, construir_senal_simulada, guardar,
    leer_captura_serial,
)


def realizar_prueba(datos, modo: int, tardias: int | None,
                   duracion_us: int | None, carpeta: Path, simulado: bool) -> dict[str, Any]:
    """Evalua una captura sin modificar sus muestras originales."""
    resultado = analizar(datos, modo, FS)
    resultado['origen'] = 'SIMULACION (NO ES MEDICION)' if simulado else 'ADC FISICO DEL RECEPTOR'
    resultado['muestras_tardias'] = tardias
    resultado['duracion_captura_us'] = duracion_us
    resultado['temporizacion_advertencia'] = (
        tardias is not None and tardias > 0.05 * N
    ) or (
        duracion_us is not None and not (105000 <= duracion_us <= 145000)
    )
    resultado['validacion_preliminar'] = bool(
        resultado['todas_detectadas']
        and not resultado['saturacion_adc']
        and not resultado['temporizacion_advertencia']
    )
    guardar(datos, resultado, carpeta)
    return resultado


def guardar_resumen(resultados: list[dict[str, Any]], carpeta: Path) -> Path:
    destino = carpeta / 'resumen_dos_placas.csv'
    destino.parent.mkdir(parents=True, exist_ok=True)
    with destino.open('w', newline='', encoding='utf-8-sig') as fh:
        writer = csv.writer(fh)
        writer.writerow(['modo', 'origen', 'frecuencias_esperadas_hz',
                         'frecuencias_detectadas_hz', 'todas_detectadas',
                         'saturacion_adc', 'muestras_tardias', 'duracion_captura_us',
                         'temporizacion_advertencia', 'validacion_preliminar'])
        for r in resultados:
            writer.writerow([
                r['modo'], r['origen'],
                ';'.join(str(f) for f in EXPECTED[r['modo']]),
                ';'.join(str(int(c['frecuencia_detectada_hz'])) for c in r['componentes']),
                r['todas_detectadas'], r['saturacion_adc'], r['muestras_tardias'],
                r['duracion_captura_us'], r['temporizacion_advertencia'],
                r['validacion_preliminar'],
            ])
    return destino


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description='Controlar emisor y receptor ESP32, capturar ADC y validar frecuencias con FFT'
    )
    parser.add_argument('--emisor', help='Puerto COM del ESP32 EMISOR, por ejemplo COM6')
    parser.add_argument('--receptor', help='Puerto COM del ESP32 RECEPTOR, por ejemplo COM7')
    elegir = parser.add_mutually_exclusive_group()
    elegir.add_argument('--modo', type=int, choices=sorted(EXPECTED), default=None)
    elegir.add_argument('--todos', action='store_true', help='Probar los cinco modos')
    parser.add_argument('--simular', action='store_true', help='Simulacion PC, NO fisica')
    parser.add_argument('--salida', type=Path, default=Path('datos/fisico_dos_placas'))
    parser.add_argument('--listar-puertos', action='store_true')
    args = parser.parse_args(argv)
    if args.listar_puertos:
        try:
            from serial.tools import list_ports
        except ImportError:
            parser.error('Falta pyserial: python -m pip install pyserial')
        for p in list_ports.comports():
            print(f'{p.device}: {p.description}')
        return 0
    if not args.simular:
        if not args.emisor or not args.receptor:
            parser.error('Se requieren ambos puertos: --emisor COMx --receptor COMy')
        if args.emisor.upper() == args.receptor.upper():
            parser.error('Emisor y receptor tienen que utilizar puertos COM diferentes')
    modos = list(EXPECTED) if args.todos else [args.modo or 1]
    resultados = []
    try:
        if args.simular:
            for modo in modos:
                datos = construir_senal_simulada(modo)
                resultado = realizar_prueba(datos, modo, None, None, args.salida, True)
                resultados.append(resultado)
                print(f'Modo {modo}: SIMULACION -> ' + ('OK' if resultado['validacion_preliminar'] else 'REVISAR'))
        else:
            try:
                import serial
            except ImportError as exc:
                raise RuntimeError('Falta pyserial: python -m pip install pyserial') from exc
            print(f'Emisor: {args.emisor}; receptor: {args.receptor}. Ambos a 115200 baudios.')
            with serial.Serial(args.emisor, baudrate=115200, timeout=2, write_timeout=2) as tx:
                print('Esperando inicio del emisor...')
                time.sleep(2.0)  # Algunos ESP32 reinician al abrir el puerto.
                tx.reset_input_buffer()
                for modo in modos:
                    tx.write(f'{modo}\n'.encode('ascii'))
                    tx.flush()
                    time.sleep(0.35)  # Estabilizacion sin solaparse con captura.
                    print(f'Capturando modo {modo}, objetivo: {EXPECTED[modo]} Hz...')
                    # Esta funcion abre COM del RECEPTOR, envia el modo y lee su ADC.
                    datos, tardias, duracion_us = leer_captura_serial(args.receptor, modo)
                    resultado = realizar_prueba(datos, modo, tardias, duracion_us, args.salida, False)
                    resultados.append(resultado)
                    print('  FFT: ' + ', '.join(
                        f"{c['frecuencia_esperada_hz']}Hz-> {c['frecuencia_detectada_hz']:.1f}Hz"
                        for c in resultado['componentes']))
                    print(f"  ADC: {resultado['adc_min']}..{resultado['adc_max']}, "
                          f"tardias={tardias}/{N}; duracion={duracion_us / 1000:.2f} ms; "
                          + ('APROBADO (preliminar)' if resultado['validacion_preliminar'] else 'REVISAR'))
                tx.write(b'0\n')  # Dejar al emisor en tension media.
                tx.flush()
    except (OSError, ValueError, RuntimeError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1
    ruta = guardar_resumen(resultados, args.salida)
    print(f'Archivos guardados en: {args.salida.resolve()}')
    print(f'Tabla resumen: {ruta.resolve()}')
    print('AVISO: solo datos con origen ADC FISICO son evidencia experimental.')
    return 0 if all(r['validacion_preliminar'] for r in resultados) else 2


if __name__ == '__main__':
    raise SystemExit(main())
