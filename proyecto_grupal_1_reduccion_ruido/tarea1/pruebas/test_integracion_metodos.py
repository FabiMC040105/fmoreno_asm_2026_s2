"""Pruebas para integración y corrección OLA sin intervención humana."""
from pathlib import Path
import sys
import unittest
import csv
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from filtrado_espectral import reduccion_espectral_adaptativa
from comparar_metodos import snr, mse


class TestIntegracion(unittest.TestCase):
    def test_espectral_identidad_sin_atenuacion_y_bordes(self):
        # Con umbral=0 no se modifica ningún bin, por lo que debe reconstruir
        # la señal completa, incluido n=0 y las últimas 512 muestras.
        for tam in (1024,2048,16384,16655):
            with self.subTest(n=tam):
                x=np.random.default_rng(41).standard_normal(tam)
                y=reduccion_espectral_adaptativa(x,1024,0)
                np.testing.assert_allclose(y,x,atol=1e-12,rtol=0)
                self.assertEqual(y.shape,x.shape)

    def test_referencia_congelada_no_influye_en_salida(self):
        x=np.random.default_rng(7).standard_normal(2167)
        s=np.random.default_rng(8).standard_normal(2167)
        y=reduccion_espectral_adaptativa(x,1024,0.2)
        z,meta=reduccion_espectral_adaptativa(x,1024,0.2,
                            referencia=s,devolver_detalles=True)
        np.testing.assert_array_equal(y,z)
        self.assertEqual(meta['referencia_con_mascara'].shape,s.shape)
        self.assertTrue(np.isfinite(z).all())

    def test_entradas_validas_y_parametros(self):
        with self.assertRaises(ValueError):reduccion_espectral_adaptativa(np.ones(10),999)
        with self.assertRaises(ValueError):reduccion_espectral_adaptativa(np.ones(10),1024,-.1)
        with self.assertRaises(ValueError):reduccion_espectral_adaptativa(np.ones(10),1024,1.1)
        with self.assertRaises(ValueError):reduccion_espectral_adaptativa(np.ones(10),1024,.1,referencia=np.ones(9))

    def test_metricas_entrada_con_datos_reales(self):
        for i,obj in [(1,5),(2,3),(3,0)]:
            p=ROOT/'pruebas'/f'caso_{i}'
            s=np.load(p/'limpia.npy'); x=np.load(p/'contaminada.npy')
            self.assertAlmostEqual(snr(s,x),obj,places=9)
            self.assertGreater(mse(s,x),0)

    def test_tabla_integrada(self):
        ruta=ROOT/'resultados/metricas.csv'
        if not ruta.exists():self.skipTest('Ejecutar primero comparar_metodos.py')
        with ruta.open(encoding='utf-8',newline='') as f:filas=list(csv.DictReader(f))
        self.assertEqual(len(filas),9)
        for k in (1,2,3):
            self.assertEqual(set(r['metodo'] for r in filas if int(r['caso'])==k),
                             {'Sin filtrar','Temporal','Espectral'})
            for row in (r for r in filas if int(r['caso'])==k):
                for campo in ('mse','snr_entrada_db','snr_salida_db',
                              'energia_util_conservada_pct','tiempo_por_bloque_ms'):
                    self.assertTrue(np.isfinite(float(row[campo])))
                self.assertAlmostEqual(float(row['snr_entrada_db']),{1:5,2:3,3:0}[k],places=9)


if __name__=='__main__':unittest.main()
