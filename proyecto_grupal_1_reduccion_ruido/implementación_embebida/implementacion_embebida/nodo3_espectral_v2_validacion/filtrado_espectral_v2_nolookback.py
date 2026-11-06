"""Nodo 3: supresion espectral adaptativa causal por ventanas solapadas.

Configuracion de referencia: fs=8192 Hz, FFT=1024, hop=512, Hann periodica.
La funcion es una referencia Python para validar el algoritmo antes del port C++.
No accede a la referencia limpia durante la deteccion.
"""
from __future__ import annotations

import numpy as np


FS_DEFAULT = 8192
FFT_SIZE_DEFAULT = 1024
HOP_SIZE_DEFAULT = 512
HISTORY_DEFAULT = 8


def _periodic_hann(n: int) -> np.ndarray:
    idx = np.arange(n, dtype=np.float64)
    return 0.5 - 0.5 * np.cos(2.0 * np.pi * idx / n)


def _make_frames(x: np.ndarray, n_fft: int, hop: int):
    """Prepara frames con N/2 de padding en ambos extremos."""
    window = _periodic_hann(n_fft)
    padded = np.pad(x, (hop, hop))
    remainder = (-(len(padded) - n_fft)) % hop
    if remainder:
        padded = np.pad(padded, (0, remainder))
    starts = np.arange(0, len(padded) - n_fft + 1, hop, dtype=np.int64)
    frames = np.stack([padded[start:start + n_fft] * window for start in starts])
    spectra = np.fft.rfft(frames, axis=1)
    freqs = np.fft.rfftfreq(n_fft, d=1.0 / FS_DEFAULT)
    return spectra, starts, window, freqs


def _ola_from_gains(
    spectra: np.ndarray,
    starts: np.ndarray,
    window: np.ndarray,
    gains: np.ndarray,
    signal_length: int,
    n_fft: int,
    hop: int,
) -> np.ndarray:
    """Reconstruccion OLA de una ventana (alineada con el sketch C++ actual).

    La Hann se aplica en analisis. En sintesis se suman las IFFT sin una segunda
    ventana y se normaliza por la suma de ventanas Hann, propiedad COLA a 50 %.
    """
    out = np.zeros((len(starts) - 1) * hop + n_fft, dtype=np.float64)
    norm = np.zeros_like(out)
    for frame_index, start in enumerate(starts):
        frame = np.fft.irfft(spectra[frame_index] * gains[frame_index], n=n_fft)
        out[start:start + n_fft] += frame
        norm[start:start + n_fft] += window
    original = slice(hop, hop + signal_length)
    denom = np.maximum(norm[original], 1e-12)
    result = out[original] / denom
    if not np.all(np.isfinite(result)):
        raise FloatingPointError("La reconstruccion espectral produjo valores no finitos.")
    return result


def reducir_espectral_v2(
    signal: np.ndarray,
    *,
    fs: int = FS_DEFAULT,
    n_fft: int = FFT_SIZE_DEFAULT,
    hop: int = HOP_SIZE_DEFAULT,
    history_frames: int = HISTORY_DEFAULT,
    relative_threshold: float = 0.10,
    low_magnitude_gain: float = 0.10,
    overlap_band_hz: tuple[float, float] = (850.0, 1300.0),
    guard_bands_hz: tuple[tuple[float, float], tuple[float, float]] = (
        (700.0, 850.0), (1300.0, 1450.0)
    ),
    protected_passband_hz: float = 1350.0,
    band_noise_ratio_threshold: float = 3.0,
    coherence_threshold: float = 0.65,
    incoherent_gain: float = 0.10,
    tone_search_start_hz: float = 1500.0,
    tone_coherence_threshold: float = 0.90,
    tone_local_peak_ratio: float = 6.0,
    tone_relative_floor: float = 0.15,
    tone_gain: float = 0.005,
    tone_radius_bins: int = 2,
    return_details: bool = False,
):
    """Filtra una señal mediante FFT/IFFT con decisiones adaptativas causales.

    Tres criterios complementarios:
    1. Umbral relativo por frame: conserva bins dominantes y atenúa bins débiles.
    2. Ruido de banda parcial: compara 850-1300 Hz con bandas de guarda. Solo si
       detecta un piso elevado en esa banda, atenúa bins temporalmente incoherentes,
       preservando picos sinusoidales coherentes dentro de la banda útil.
    3. Tono estrecho fuera de la banda protegida: detecta picos locales persistentes
       por coherencia de fase y prominencia espectral; atenúa el pico y sus vecinos.

    Se utiliza una ventana causal de hasta `history_frames` espectros anteriores.
    Para confirmar una interferencia tonal se retiene un frame previo (look-back de
    un hop), que se vuelve a sintetizar cuando el detector obtiene evidencia.

    La referencia limpia NO forma parte de la deteccion. Para evaluacion offline,
    `frame_gains` permite aplicar exactamente las mismas ganancias a una referencia.
    """
    x = np.asarray(signal, dtype=np.float64)
    if x.ndim != 1 or x.size == 0 or not np.all(np.isfinite(x)):
        raise ValueError("La entrada debe ser un vector 1D, finito y no vacio.")
    if fs != FS_DEFAULT:
        raise ValueError("Esta version se valida actualmente a 8192 Hz.")
    if n_fft != 1024 or hop != n_fft // 2:
        raise ValueError("La version actual requiere FFT=1024 y solapamiento del 50 %.")
    if history_frames < 2:
        raise ValueError("history_frames debe ser >= 2.")
    if not 0.0 <= relative_threshold <= 1.0:
        raise ValueError("relative_threshold debe estar entre 0 y 1.")

    spectra, starts, window, freqs = _make_frames(x, n_fft, hop)
    frame_count, bin_count = spectra.shape
    gains_all = np.ones((frame_count, bin_count), dtype=np.float64)
    synthesis_frames: list[np.ndarray] = []
    raw_history: list[np.ndarray] = []
    magnitude_history: list[np.ndarray] = []

    # Para hop=N/2, la fase esperada del bin k cambia por (-1)^k por frame.
    bin_sign = np.where(np.arange(bin_count) % 2, -1.0, 1.0)
    partial_band_ratios: list[float] = []
    partial_band_active: list[bool] = []
    detected_tones: list[dict] = []
    coherent_peak_history: list[list[int]] = []

    band_lo, band_hi = overlap_band_hz
    band_mask = (freqs >= band_lo) & (freqs <= band_hi)
    passband_mask = freqs <= protected_passband_hz
    guard_mask = np.zeros(bin_count, dtype=bool)
    for low, high in guard_bands_hz:
        guard_mask |= (freqs >= low) & (freqs < high if high != 1450.0 else freqs <= high)
    high_mask = freqs >= tone_search_start_hz
    high_indices = np.flatnonzero(high_mask)

    for frame_index, spectrum in enumerate(spectra):
        current_mag = np.abs(spectrum)
        current_max = float(np.max(current_mag))
        threshold = current_max * relative_threshold
        gains = np.where(current_mag < threshold, low_magnitude_gain, 1.0)

        raw_history.append(spectrum.copy())
        magnitude_history.append(current_mag)
        if len(raw_history) > history_frames:
            raw_history.pop(0)
            magnitude_history.pop(0)

        hist = np.stack(raw_history)
        hist_mag = np.stack(magnitude_history)
        mean_mag = np.mean(hist_mag, axis=0)
        enough_history = len(raw_history) >= 2

        if enough_history:
            # Coherencia exacta a centros de bin: útil para distinguir tonos
            # coherentes de ruido aleatorio en una banda parcialmente solapada.
            local_index = np.arange(len(raw_history), dtype=np.float64)[:, None]
            sign_history = np.where(
                (local_index.astype(np.int64) % 2) == 1,
                bin_sign[None, :],
                1.0,
            )
            corrected_integer = hist * sign_history
            coherence_integer = (
                np.abs(np.mean(corrected_integer, axis=0)) / (mean_mag + 1e-15)
            )

            # Coherencia con estimacion de desplazamiento sub-bin. Se usa solo
            # para el detector de tonos, así se reconocen interferencias como
            # 1795 Hz aunque no coincidan exactamente con el bin de 8 Hz.
            phase_products = (
                hist[1:] * np.conj(hist[:-1]) * bin_sign[None, :]
            )
            residual_phase_step = np.angle(np.sum(phase_products, axis=0))
            corrected_fractional = corrected_integer * np.exp(
                -1j * local_index * residual_phase_step[None, :]
            )
            coherence_fractional = (
                np.abs(np.mean(corrected_fractional, axis=0)) / (mean_mag + 1e-15)
            )

            # Picos coherentes en banda útil: se protege su lóbulo principal +/-2 bins.
            max_passband_mag = float(np.max(mean_mag[passband_mask]))
            coherent_peak_threshold = 0.05 * max_passband_mag
            coherent_peaks = np.flatnonzero(
                passband_mask
                & (coherence_integer >= 0.80)
                & (mean_mag >= coherent_peak_threshold)
            )
            protected = np.zeros(bin_count, dtype=bool)
            for k in coherent_peaks:
                lo = max(0, int(k) - 2)
                hi = min(bin_count, int(k) + 3)
                protected[lo:hi] = True
            coherent_peak_history.append(coherent_peaks.astype(int).tolist())

            # La compuerta adicional solo se activa ante una banda de ruido
            # realmente elevada respecto a las bandas vecinas.
            residual_band = band_mask & (~protected)
            band_floor = float(np.mean(mean_mag[residual_band])) if np.any(residual_band) else 0.0
            guard_floor = float(np.mean(mean_mag[guard_mask])) if np.any(guard_mask) else 0.0
            band_ratio = band_floor / (guard_floor + 1e-15)
            band_noise_present = band_ratio >= band_noise_ratio_threshold
            partial_band_ratios.append(float(band_ratio))
            partial_band_active.append(bool(band_noise_present))

            if band_noise_present:
                incoherent = band_mask & (coherence_integer < coherence_threshold) & (~protected)
                gains[incoherent] *= incoherent_gain
                gains[protected] = 1.0

            # Detector de tonos fuera de la banda útil protegida.
            tone_bins: list[int] = []
            high_floor = (
                tone_relative_floor * float(np.max(mean_mag[high_indices]))
                if high_indices.size else float("inf")
            )
            for k in high_indices:
                k = int(k)
                if k < 6 or k + 6 >= bin_count:
                    continue
                # Solo máximos locales; se compara con un vecindario que excluye
                # el lóbulo central y sus dos bins adyacentes.
                if not (mean_mag[k] >= mean_mag[k - 1] and mean_mag[k] > mean_mag[k + 1]):
                    continue
                neighbors = np.concatenate((mean_mag[k - 6:k - 1], mean_mag[k + 2:k + 7]))
                local_floor = float(np.mean(neighbors)) + 1e-15
                prominence_ratio = float(mean_mag[k] / local_floor)
                if (
                    mean_mag[k] >= high_floor
                    and prominence_ratio >= tone_local_peak_ratio
                    and coherence_fractional[k] >= tone_coherence_threshold
                ):
                    if not any(abs(k - existing) <= tone_radius_bins for existing in tone_bins):
                        tone_bins.append(k)

            for k in tone_bins:
                lo = max(0, k - tone_radius_bins)
                hi = min(bin_count, k + tone_radius_bins + 1)
                gains[lo:hi] = np.minimum(gains[lo:hi], tone_gain)
                # Retener el frame previo un hop permite aplicar el notch al inicio
                # de un tono persistente sin esperar a que avance toda la ventana.
                # Streaming-compatible variant: no retroactive modification of prior frames.
            if tone_bins:
                detected_tones.append({
                    "frame": int(frame_index),
                    "bins": tone_bins,
                    "frequencies_hz": [float(freqs[k]) for k in tone_bins],
                })
        else:
            partial_band_ratios.append(float("nan"))
            partial_band_active.append(False)
            coherent_peak_history.append([])

        gains_all[frame_index] = gains
        synthesis_frames.append(np.fft.irfft(spectrum * gains, n=n_fft))

    # OLA de la señal recibida. La ventana se aplica en análisis y se normaliza
    # por suma de Hann, igual que el principio usado en fft_ola.h.
    output = np.zeros((len(starts) - 1) * hop + n_fft, dtype=np.float64)
    normalization = np.zeros_like(output)
    for start, frame in zip(starts, synthesis_frames):
        output[start:start + n_fft] += frame
        normalization[start:start + n_fft] += window
    original = slice(hop, hop + len(x))
    y = output[original] / np.maximum(normalization[original], 1e-12)
    if not np.all(np.isfinite(y)):
        raise FloatingPointError("La salida FFT v2 contiene valores no finitos.")

    if not return_details:
        return y

    details = {
        "frame_gains": gains_all,
        "frame_count": int(frame_count),
        "fft_size": int(n_fft),
        "hop_size": int(hop),
        "overlap_percent": 100.0 * (1.0 - hop / n_fft),
        "history_frames": int(history_frames),
        "partial_band_ratios": partial_band_ratios,
        "partial_band_active": partial_band_active,
        "partial_band_active_fraction": float(np.mean(partial_band_active)),
        "detected_tones": detected_tones,
        "coherent_passband_bins": coherent_peak_history,
        "tone_gain": float(tone_gain),
        "incoherent_gain": float(incoherent_gain),
        "one_hop_lookback": False,
        "window": "Hann periodica",
        "synthesis": "IFFT + OLA, normalizacion por suma de Hann (COLA)",
    }
    return y, details


def aplicar_ganancias_a_referencia(
    reference: np.ndarray,
    details: dict,
    *,
    fs: int = FS_DEFAULT,
    n_fft: int = FFT_SIZE_DEFAULT,
    hop: int = HOP_SIZE_DEFAULT,
) -> np.ndarray:
    """Aplica a una referencia offline las ganancias aprendidas SOLO de la mezcla."""
    s = np.asarray(reference, dtype=np.float64)
    if s.ndim != 1 or s.size == 0 or not np.all(np.isfinite(s)):
        raise ValueError("La referencia debe ser un vector 1D finito no vacio.")
    if fs != FS_DEFAULT or n_fft != FFT_SIZE_DEFAULT or hop != HOP_SIZE_DEFAULT:
        raise ValueError("La referencia requiere fs=8192, FFT=1024 y hop=512.")
    spectra, starts, window, _ = _make_frames(s, n_fft, hop)
    gains = np.asarray(details["frame_gains"], dtype=np.float64)
    if gains.shape != spectra.shape:
        raise ValueError("Las ganancias aprendidas no coinciden con la referencia.")
    return _ola_from_gains(spectra, starts, window, gains, len(s), n_fft, hop)
