"""Pruebas numericas del filtro temporal y de su estado entre bloques.

Desde tarea1: python -m unittest discover -s pruebas -p "test_filtros_temporales.py" -v
"""
import sys
import unittest
from pathlib import Path
import numpy as np
from scipy import signal

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))
from temporal_datos import cargar_entradas
from evaluar_hardware_temporal import codificar_dac, ATOL_FLOAT32
from filtros_temporales import disenar_filtro, filtrar_sos_propio, filtrar_por_bloques


class TestFiltroTemporal(unittest.TestCase):
    """Verifica la ecuacion propia y su continuidad, sin generar archivos.

    La referencia es scipy.signal.sosfilt con reposo inicial. Se comparan
    salidas, no estados internos: SciPy usa forma directa II transpuesta
    y nuestra implementacion forma directa I.
    Tolerancia absoluta: 1e-12; relativa: 0. Es una prueba numerica de
    implementacion en float64, no una medida de reduccion de ruido.
    """

    ATOL = 1e-12

    @classmethod
    def setUpClass(cls):
        cls.config, cls.casos = cargar_entradas()
        cls.sos = np.asarray(disenar_filtro(cls.config["fs_hz"])["sos"])

    def test_tres_casos_contra_scipy(self):
        """Contrasta las tres mezclas completas con una referencia externa."""
        for numero, datos in sorted(self.casos.items()):
            with self.subTest(caso=numero):
                x = datos["contaminada"]
                salida, _ = filtrar_por_bloques(x, self.sos, self.config["n_bloque"])
                referencia = signal.sosfilt(self.sos, x)
                np.testing.assert_allclose(salida, referencia, atol=self.ATOL, rtol=0)
                error = float(np.max(np.abs(salida - referencia)))
                print(f"Caso {numero}: error maximo contra SciPy = {error:.3e}")

    def test_impulso_y_escalon_contra_scipy(self):
        """Comprueba arranque y transitorios con entradas deterministas."""
        impulso = np.zeros(2048)
        impulso[0] = 1
        for nombre, x in (("impulso", impulso), ("escalon", np.ones(2048))):
            with self.subTest(entrada=nombre):
                salida, _ = filtrar_sos_propio(x, self.sos)
                np.testing.assert_allclose(salida, signal.sosfilt(self.sos, x),
                                           atol=self.ATOL, rtol=0)

    def test_bloques_equivalentes_a_senal_completa(self):
        """Incluye bloques unitarios y una longitud que no divide la senal."""
        x = np.random.default_rng(20261014).standard_normal(2051)
        completa, estado_completo = filtrar_sos_propio(x, self.sos)
        for longitud in (1, 73, 1024, len(x) + 1):
            with self.subTest(n_bloque=longitud):
                salida, estado = filtrar_por_bloques(x, self.sos, longitud)
                self.assertEqual(salida.shape, x.shape)
                # Misma ecuacion y orden de operaciones: igualdad exacta.
                np.testing.assert_array_equal(salida, completa)
                np.testing.assert_array_equal(estado, estado_completo)

    def test_continuidad_entre_llamadas(self):
        """Reanuda con estado no nulo, incluso tras recibir un bloque vacio."""
        x = self.casos[3]["contaminada"][:2051]
        primera, estado = filtrar_por_bloques(x[:137], self.sos, 73)
        estado_guardado = estado.copy()
        vacia, siguiente = filtrar_sos_propio([], self.sos, estado)
        self.assertEqual(vacia.size, 0)
        np.testing.assert_array_equal(siguiente, estado_guardado)
        segunda, final = filtrar_por_bloques(x[137:], self.sos, 511, siguiente)
        np.testing.assert_array_equal(estado, estado_guardado)
        np.testing.assert_array_equal(siguiente, estado_guardado)
        completa, final_completo = filtrar_sos_propio(x, self.sos)
        np.testing.assert_array_equal(np.concatenate((primera, segunda)), completa)
        np.testing.assert_array_equal(final, final_completo)
        np.testing.assert_allclose(completa, signal.sosfilt(self.sos, x),
                                   atol=self.ATOL, rtol=0)

    def test_coeficientes_no_normalizados(self):
        """Multiplicar numerador y denominador no debe cambiar H(z)."""
        x = np.random.default_rng(21).standard_normal(513)
        escalados = self.sos * np.arange(2, len(self.sos) + 2)[:, None]
        copia_coef = escalados.copy()
        copia_x = x.copy()
        salida, _ = filtrar_sos_propio(x, escalados)
        np.testing.assert_allclose(salida, signal.sosfilt(self.sos, x),
                                   atol=self.ATOL, rtol=0)
        np.testing.assert_array_equal(escalados, copia_coef)
        np.testing.assert_array_equal(x, copia_x)

    def test_rechazo_de_entradas_invalidas(self):
        """Evita ejecutar con dimensiones, muestras o estados invalidos."""
        for entrada in (np.zeros((2, 2)), [np.nan], [np.inf], [1j]):
            with self.subTest(entrada=str(entrada)):
                with self.assertRaises(ValueError):
                    filtrar_sos_propio(entrada, self.sos)
        with self.assertRaises(ValueError):
            filtrar_sos_propio([1], self.sos, np.zeros((len(self.sos), 2)))
        malos = self.sos.copy()
        malos[0, 3] = 0
        with self.assertRaises(ValueError):
            filtrar_sos_propio([1], malos)
        for longitud in (0, -1, 1.5):
            with self.subTest(n_bloque=longitud):
                with self.assertRaises(ValueError):
                    filtrar_por_bloques([1], self.sos, longitud)


    def test_float32_precision_y_referencia(self):
        """Compara float32 propio contra float64 propio y float32 de SciPy."""
        for numero, caso in self.casos.items():
            with self.subTest(caso=numero):
                x = caso["contaminada"]
                y32, estado = filtrar_por_bloques(x, self.sos, 1024, dtype=np.float32)
                self.assertEqual(y32.dtype, np.dtype(np.float32))
                self.assertEqual(estado.dtype, np.dtype(np.float32))
                y64, _ = filtrar_sos_propio(x, self.sos)
                referencia = signal.sosfilt(self.sos.astype(np.float32), x.astype(np.float32))
                np.testing.assert_allclose(y32, y64, atol=ATOL_FLOAT32, rtol=0)
                np.testing.assert_allclose(y32, referencia, atol=ATOL_FLOAT32, rtol=0)

    def test_float32_continuidad(self):
        """Un corte irregular y una llamada vacia preservan los estados float32."""
        x = self.casos[3]["contaminada"][:2051]
        y, estado = filtrar_sos_propio(x, self.sos, dtype=np.float32)
        a, z = filtrar_por_bloques(x[:137], self.sos, 73, dtype=np.float32)
        _, z = filtrar_sos_propio([], self.sos, z, dtype=np.float32)
        b, final = filtrar_por_bloques(x[137:], self.sos, 73, z, dtype=np.float32)
        np.testing.assert_array_equal(np.r_[a, b], y)
        np.testing.assert_array_equal(final, estado)
        for dtype in (np.int16, np.float16):
            with self.assertRaises(ValueError):
                filtrar_sos_propio(x, self.sos, dtype=dtype)

    def test_dac_saturacion_y_cuantizacion(self):
        """Verifica extremos, recorte sin wraparound y cota de medio LSB."""
        codigos, _, recortes = codificar_dac([-2, -1, 0, 1, 2])
        np.testing.assert_array_equal(codigos, [0, 0, 128, 255, 255])
        self.assertEqual(recortes, 2)
        x = np.linspace(-1, 1, 10001)
        _, reconstruida, recortes = codificar_dac(x)
        self.assertEqual(recortes, 0)
        self.assertLessEqual(np.max(np.abs(reconstruida-x)), 1/255 + 1e-15)


if __name__ == "__main__":
    unittest.main()
