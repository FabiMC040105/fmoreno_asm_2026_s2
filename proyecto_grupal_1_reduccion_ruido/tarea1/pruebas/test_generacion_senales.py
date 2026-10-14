"""Pruebas de consistencia para los datos compartidos con los filtros 2.3/2.4.
Ejecutar: python -m unittest discover -s pruebas -p 'test_*.py' -v
"""
import sys
import unittest
from pathlib import Path
import numpy as np
from scipy.io import wavfile

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))
from generacion_senales import (CASOS, FS, N_BLOQUE, L, TONOS_HZ,
                                BANDAS_HZ, energia_por_bandas, generar, snr_db)


class TestGeneracion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        generar()  # autocontenido, regenera los datos incluso si se borraron

    def test_reproducibilidad(self):
        anterior = [np.load(RAIZ / "pruebas" / f"caso_{c['id']}" / "ruido.npy")
                    for c in CASOS]
        generar()
        for c, esperado in zip(CASOS, anterior):
            real = np.load(RAIZ / "pruebas" / f"caso_{c['id']}" / "ruido.npy")
            np.testing.assert_array_equal(real, esperado)

    def test_snr_exacta_y_suma(self):
        self.assertEqual(len({c["semilla"] for c in CASOS}), 3)
        for caso in CASOS:
            p = RAIZ / "pruebas" / f"caso_{caso['id']}"
            s, r, x = [np.load(p / f"{n}.npy") for n in ("limpia", "ruido", "contaminada")]
            self.assertEqual(len(s), L)
            np.testing.assert_allclose(s+r, x, atol=1e-12, rtol=0)
            self.assertAlmostEqual(snr_db(s, x), caso["snr_objetivo_db"], places=9)
            self.assertLessEqual(np.max(np.abs(x)), .9500001)
            energia_por_bandas(x)  # internamente verifica Parseval
            for n in ("limpia", "ruido", "contaminada"):
                fs, v = wavfile.read(p / f"{n}.wav")
                self.assertEqual(fs, FS)
                self.assertEqual(v.dtype, np.float32)
                np.testing.assert_allclose(v, np.load(p / f"{n}.npy"), atol=5e-8, rtol=0)

    def test_solapamiento_y_banda_separada(self):
        self.assertEqual(FS % N_BLOQUE, 0)
        self.assertTrue(N_BLOQUE & (N_BLOQUE - 1) == 0)
        caso1 = CASOS[0]
        self.assertTrue(all(abs(caso1["interferencia_hz"]-f) > 200 for f in TONOS_HZ))
        bajo, alto = CASOS[2]["banda_ruido_hz"]
        self.assertTrue(bajo < TONOS_HZ[-1] < alto)
        for caso in (CASOS[0], CASOS[2]):
            p = RAIZ / "pruebas" / f"caso_{caso['id']}"
            r = np.load(p / "ruido.npy")
            bandas = energia_por_bandas(r)
            if caso["id"] == 1:
                self.assertGreater(bandas[5], 99.999)
            else:
                self.assertGreater(bandas[3], 40.0)  # 900-1150: contiene el tono 1024


if __name__ == "__main__":
    unittest.main()
