function X = mi_dft(x)
  % Calcula la DFT directamente a partir de su definicion.
  % Entrada: x, muestras de la senal.
  % Salida: X, coeficientes complejos de frecuencia.

  N = length(x);
  X = zeros(1, N);

  % Recorremos las frecuencias que vamos a analizar.
  for k = 0:N-1

    % Sumamos el aporte de cada muestra.
    for n = 0:N-1
      X(k+1) = X(k+1) + x(n+1) * exp(-1i*2*pi*k*n/N);
    endfor

  endfor
endfunction
