"""Pruebas de integración Semana 12; no requieren conectar ESP32.

    python -m unittest discover -s semana12_asm/pruebas -p 'test_*.py' -v
"""
import importlib.util
from pathlib import Path
import tempfile
import unittest
import numpy as np

SCRIPT = Path(__file__).resolve().parents[1] / 'python' / 'prototipo_alto_nivel.py'
spec = importlib.util.spec_from_file_location('prototipo_alto_nivel', SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class PrototipoTests(unittest.TestCase):
    def test_parametros_y_nyquist(self):
        mod.validar_parametros()
        self.assertEqual(mod.FS / mod.N, 8)

    def test_todos_los_modos_tienen_frecuencias_correctas(self):
        for modo, frecuencias in mod.TONOS.items():
            with self.subTest(modo=modo):
                y = mod.forma_emisor(modo)
                self.assertEqual(len(y), 1024)
                self.assertTrue(np.all((y >= 0) & (y <= 255)))
                f, amplitud = mod.espectro(y)
                pico_max = np.max(amplitud[1:])
                for hz in frecuencias:
                    self.assertGreater(amplitud[int(hz/8)], .04*pico_max)
                self.assertEqual(float(f[int(frecuencias[0]/8)]), frecuencias[0])

    def test_csv_y_figuras_generadas(self):
        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp)
            filas = mod.fig_modos(destino)
            self.assertEqual(len(filas), 5)
            for i in range(1, 6):
                self.assertTrue((destino / f'modelo_modo{i}.png').is_file())
                self.assertTrue((destino / f'senal_modo{i}.csv').is_file())

    def test_datos_fisicos_si_estan_disponibles(self):
        ruta = mod.BASE_DIR / 'datos' / 'fisico_dos_placas'
        if not ruta.exists():
            self.skipTest('No se adjuntaron capturas físicas en este paquete de integración')
        with tempfile.TemporaryDirectory() as tmp:
            reportes = mod.revisar_capturas(Path(tmp))
            self.assertEqual(len(reportes), 5)
            self.assertTrue(all(r['muestras'] == mod.N for r in reportes))
            self.assertTrue(all(r['validacion_preliminar'] for r in reportes))

    def test_filtros_originales_si_estan_disponibles(self):
        if not (mod.TAREA1 / 'src' / 'filtros_temporales.py').is_file():
            self.skipTest('La Tarea 1 todavía no se ha integrado')
        with tempfile.TemporaryDirectory() as tmp:
            rows = mod.simulaciones_con_filtros(Path(tmp))
            self.assertEqual(len(rows), 9)
            snr_entrada = {r['caso']:r['SNR_entrada_db'] for r in rows}
            for caso, esperado in [(1,5.0),(2,3.0),(3,0.0)]:
                self.assertAlmostEqual(snr_entrada[caso], esperado, places=6)
            self.assertTrue(all(np.isfinite(r['MSE']) for r in rows))

if __name__ == '__main__':
    unittest.main()
