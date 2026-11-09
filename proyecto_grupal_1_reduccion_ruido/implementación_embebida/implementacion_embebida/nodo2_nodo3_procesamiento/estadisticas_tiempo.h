#pragma once
#include <math.h>
#include <stdint.h>

// Media, minimo, maximo y desviacion estandar poblacional acumulados.
// No guarda un historial de muestras ni usa memoria dinamica.
struct EstadisticasTiempo {
  uint32_t cantidad = 0;
  uint32_t minimo = UINT32_MAX;
  uint32_t maximo = 0;
  double media = 0.0;
  double m2 = 0.0;

  void agregar(uint32_t microsegundos) {
    ++cantidad;
    if (microsegundos < minimo) minimo = microsegundos;
    if (microsegundos > maximo) maximo = microsegundos;
    const double delta = (double)microsegundos - media;
    media += delta / (double)cantidad;
    const double delta2 = (double)microsegundos - media;
    m2 += delta * delta2;
  }
  double desviacion() const {
    return cantidad > 0 ? sqrt(m2 / (double)cantidad) : 0.0;
  }
  uint32_t minSeguro() const { return cantidad ? minimo : 0; }
};
