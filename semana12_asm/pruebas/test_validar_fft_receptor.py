"""Pruebas de software del analizador. NO validan fisicamente el hardware."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

path = Path(__file__).resolve().parents[1] / 'python' / 'validar_fft_receptor.py'
spec = importlib.util.spec_from_file_location('validar_fft_receptor', path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class FFTTests(unittest.TestCase):
    def test_todos_los_modos_simulados(self):
        for modo, esperado in mod.EXPECTED.items():
            with self.subTest(modo=modo):
                datos = mod.construir_senal_simulada(modo)
                self.assertEqual(len(datos), 1024)
                reporte = mod.analizar(datos, modo)
                self.assertTrue(reporte['todas_detectadas'], reporte)
                self.assertFalse(reporte['saturacion_adc'])
                self.assertEqual([c['frecuencia_esperada_hz'] for c in reporte['componentes']], esperado)

    def test_longitud_incorrecta(self):
        import numpy as np
        with self.assertRaises(ValueError):
            mod.analizar(np.ones(20), 1)

    def test_exportacion(self):
        with tempfile.TemporaryDirectory() as d:
            datos = mod.construir_senal_simulada(4)
            reporte = mod.analizar(datos, 4)
            mod.guardar(datos, reporte, Path(d))
            for p in ['captura_modo4.csv', 'reporte_modo4.json', 'fft_modo4.png']:
                self.assertTrue((Path(d) / p).exists(), p)


if __name__ == '__main__':
    unittest.main()
