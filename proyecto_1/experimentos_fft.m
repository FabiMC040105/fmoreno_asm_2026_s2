% Experimentos con DFT y FFT
% Integrantes: Fabiana María Moreno Castrillo
%              Andrés Enrique Blanco Coto

clear;
clc;
close all;

% Parametros de la señal
Fs = 1000;       % Frecuencia de muestreo: 1000 muestras por segundo
N = 200;         % Cantidad de muestras
f0 = 50;        % Frecuencia de la onda en Hz

% Instantes de tiempo y valores de la señal
t = (0:N-1) / Fs;
x = sin(2*pi*f0*t);

% Gráfica de la señal en el tiempo
figure;
plot(t, x, 'b');
grid on;
xlabel('Tiempo (s)');
ylabel('Amplitud');
title('Señal senoidal de 50 Hz');

% Calculamos la DFT con nuestra propia funcion.
X_dft = mi_dft(x);

% Mostramos cuantos coeficientes se calcularon.
disp('Cantidad de coeficientes de la DFT:');
disp(length(X_dft));


% Frecuencia en Hz correspondiente a cada coeficiente.
f = (0:N-1) * Fs / N;

% Magnitud normalizada de la DFT.
magnitud = abs(X_dft) / N;

% Mostramos las frecuencias desde 0 hasta Fs/2.
indices = 1:(floor(N/2) + 1);

figure;
stem(f(indices), magnitud(indices), 'b');
grid on;
xlabel('Frecuencia (Hz)');
ylabel('Magnitud |X|/N');
title('Magnitud de la DFT');
xlim([0 Fs/2]);
