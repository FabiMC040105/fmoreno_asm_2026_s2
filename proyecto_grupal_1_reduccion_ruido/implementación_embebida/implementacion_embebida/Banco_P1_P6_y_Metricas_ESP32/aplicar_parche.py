#!/usr/bin/env python3
"""Aplica la instrumentacion a una COPIA de nodo2_nodo3_procesamiento.ino.
No cambia filtros ni parametros de DSP. No parchea por duplicado.
Uso: py aplicar_parche.py "RUTA_A_CARPETA_nodo2_nodo3_procesamiento"
"""
from pathlib import Path
import sys
import shutil

if len(sys.argv) != 2:
    sys.exit('Uso: py aplicar_parche.py "C:\\ruta\\nodo2_nodo3_procesamiento"')
folder = Path(sys.argv[1]).expanduser().resolve()
ino = folder / 'nodo2_nodo3_procesamiento.ino'
if not ino.is_file():
    sys.exit(f'ERROR: no existe {ino}')
if not (folder / 'fft_ola_v2_stream.h').exists() or not (folder / 'fir_esp32.h').exists():
    sys.exit('ERROR: faltan headers originales; revise carpeta.')
source = ino.read_text(encoding='utf-8')
if '#include "metricas_receptor.h"' in source:
    sys.exit('YA INSTRUMENTADO: no aplico cambios por duplicado.')
anchor1 = '#include "fft_ola_v2_stream.h"'
anchor2 = '  ++packetsOk;'
assert source.count(anchor1)==1, 'No coincide include de la version actual.'
assert source.count(anchor2)==1, 'No coincide contador de paquetes de la version actual.'
call = '''  // Telemetria del receptor: se emite una fila MTR cada 8 bloques.
  // El tiempo ADC proviene de Nodo1; no es latencia extremo a extremo.
  metricas_asm::registrar(inputBlock, firBlock, fftBlock, BLOCK_SAMPLES,
      lastSequence, flags, packetsOk, packetsBadCrc,
      packetsBadFormat, sequenceGaps, dacErrors,
      readU32LE(headerRest + 18), processingUs, i2sWriteUs,
      sizeof(SpectralOLA1024V2Stream));
'''
new = source.replace(anchor1, anchor1+'\n#include "metricas_receptor.h"',1)
new = new.replace(anchor2, anchor2+'\n'+call,1)
backup = ino.with_suffix('.ino.antes_metricas.bak')
if backup.exists():
    sys.exit(f'ERROR: ya existe backup {backup}; no sobreescribir automaticamente.')
shutil.copy2(ino, backup)
shutil.copy2(Path(__file__).with_name('metricas_receptor.h'), folder / 'metricas_receptor.h')
ino.write_text(new, encoding='utf-8')
print('OK: instrumentacion aplicada; original guardado en', backup)
print('Verifique y suba nodo2_nodo3_procesamiento.ino en Arduino IDE.')
