% Comparacion de tiempos de nuestras implementaciones.
clear;
clc;
close all;

tamanos = [64 128 256 512 1024];
repeticiones = 3;

tiempos_dft = zeros(size(tamanos));
tiempos_fft = zeros(size(tamanos));
errores = zeros(size(tamanos));

% Primera llamada para cargar las funciones antes de medir.
mi_dft([1 2 3 4]);
mi_fft([1 2 3 4]);

fprintf(' N       DFT (s)       FFT (s)      DFT/FFT\n');

for i = 1:length(tamanos)
  N = tamanos(i);
  n = 0:N-1;

  % Dos componentes que completan ciclos enteros en el registro.
  x = sin(2*pi*5*n/N) + 0.5*cos(2*pi*12*n/N);

  td = zeros(1, repeticiones);
  tf = zeros(1, repeticiones);

  for r = 1:repeticiones
    tic;
    X_dft = mi_dft(x);
    td(r) = toc;

    tic;
    X_fft = mi_fft(x);
    tf(r) = toc;
  endfor

  % Usamos la mediana para reducir el efecto de mediciones fuera de lo normal.
  tiempos_dft(i) = median(td);
  tiempos_fft(i) = median(tf);

  % Comprobamos tambien que los resultados coincidan.
  errores(i) = max(abs(X_dft - X_fft));
  assert(errores(i) < 1e-8, 'Las transformadas no coinciden.');

  fprintf('%4d    %.6f      %.6f      %.2f\n', ...
          N, tiempos_dft(i), tiempos_fft(i), ...
          tiempos_dft(i)/tiempos_fft(i));
endfor

figure;
loglog(tamanos, tiempos_dft, '-o', ...
       tamanos, tiempos_fft, '-s');
grid on;
xlabel('Cantidad de muestras N');
ylabel('Tiempo (s)');
title('Tiempos de nuestras implementaciones DFT y FFT');
legend('DFT directa', 'FFT propia', 'location', 'northwest');

if ~exist('resultados', 'dir')
  mkdir('resultados');
endif

print('resultados/comparacion_tiempos.png', '-dpng', '-r150');

% Columnas: N, segundos DFT, segundos FFT, error maximo.
datos = [tamanos(:), tiempos_dft(:), tiempos_fft(:), errores(:)];
save('-ascii', 'resultados/tiempos.txt', 'datos');
