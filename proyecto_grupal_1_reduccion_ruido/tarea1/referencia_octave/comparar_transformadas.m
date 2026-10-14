% Verificacion de nuestra DFT y nuestra FFT.
clear;
clc;
close all;

% Usamos 256 muestras porque nuestra FFT requiere potencia de 2.
Fs = 1024;
N = 256;
t = (0:N-1) / Fs;

% Senal con dos frecuencias conocidas.
x = sin(2*pi*64*t) + 0.5*cos(2*pi*128*t);

% Calculamos la misma transformada de tres maneras.
X_dft = mi_dft(x);
X_fft = mi_fft(x);
X_referencia = fft(x);

% Mayor diferencia entre los coeficientes calculados.
error_dft_fft = max(abs(X_dft - X_fft));
error_fft_ref = max(abs(X_fft - X_referencia));

fprintf('Error entre nuestra DFT y FFT: %.3e\n', error_dft_fft);
fprintf('Error entre nuestra FFT y la de Octave: %.3e\n', error_fft_ref);

% Verificacion con una tolerancia numerica pequena.
tolerancia = 1e-9;

assert(error_dft_fft < tolerancia, ...
       'La DFT y la FFT no coinciden dentro de la tolerancia.');

assert(error_fft_ref < tolerancia, ...
       'Nuestra FFT no coincide con la de Octave.');

disp('Verificacion correcta para esta senal.');
