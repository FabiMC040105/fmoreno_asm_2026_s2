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
% Mezclamos dos ondas de distinta frecuencia y amplitud.
x1 = sin(2*pi*50*t);          % Onda de 50 Hz, amplitud 1
x2 = 0.5*cos(2*pi*120*t);     % Onda de 120 Hz, amplitud 0.5
x = x1 + x2;

% Gráfica de la señal en el tiempo
figure;
plot(t, x, 'b');
grid on;
xlabel('Tiempo (s)');
ylabel('Amplitud');
title('Mezcla de ondas de 50 Hz y 120 Hz');

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


% Fase en grados de los coeficientes de la DFT.
fase = angle(X_dft) * 180 / pi;

% Mostramos fase solo donde la magnitud es significativa.
% En coeficientes casi nulos, la fase no es interpretable.
umbral = 1e-6 * max(magnitud);
validos = indices(magnitud(indices) > umbral);

figure;
stem(f(validos), fase(validos), 'b');
grid on;
xlabel('Frecuencia (Hz)');
ylabel('Fase (grados)');
title('Fase de la DFT');
xlim([0 Fs/2]);
ylim([-180 180]);



% Guardamos las graficas para el informe.
if ~exist('resultados', 'dir')
  mkdir('resultados');
endif

figure(1);
print('resultados/mezcla_tiempo.png', '-dpng', '-r150');

figure(2);
print('resultados/mezcla_magnitud.png', '-dpng', '-r150');

figure(3);
print('resultados/mezcla_fase.png', '-dpng', '-r150');
