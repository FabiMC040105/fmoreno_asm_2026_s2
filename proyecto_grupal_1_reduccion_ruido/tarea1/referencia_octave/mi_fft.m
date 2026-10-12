function X = mi_fft(x)
  % FFT radix-2: divide la senal en dos grupos y combina resultados.
  % Entrada: vector de muestras cuya longitud sea potencia de 2.
  % Salida: coeficientes complejos de la DFT.

  x = x(:).';  % Convertimos la entrada en un vector fila.
  N = length(x);

  if N < 1 || 2^nextpow2(N) ~= N
    error('La cantidad de muestras debe ser una potencia de 2.');
  endif

  % Con una sola muestra, la transformada es esa misma muestra.
  if N == 1
    X = x;
    return;
  endif

  % Separamos los indices matematicos pares e impares.
  pares = mi_fft(x(1:2:end));
  impares = mi_fft(x(2:2:end));

  % Factores complejos necesarios para combinar ambos grupos.
  k = 0:(N/2 - 1);
  W = exp(-1i*2*pi*k/N);

  % Construimos las dos mitades del resultado.
  X = [pares + W.*impares, pares - W.*impares];
endfunction
