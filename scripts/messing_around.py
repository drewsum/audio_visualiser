import numpy as np
import matplotlib.pyplot as plt
import scipy.signal as signal # type: ignore

fc = [10, 20, 40, 80, 160, 320, 640, 1280, 2560, 5120, 10240, 20480]  # Cutoff frequencies in Hz

# Plot the response
plt.figure()

for frequency in fc:
    # Design a Butterworth low-pass filter
    b, a = signal.butter(3, [frequency*0.9, frequency*1.1], 'band', analog=True)
    w, h = signal.freqs(b, a)
    plt.semilogx(w, 20 * np.log10(abs(h)))


# Plot the response
plt.title('Bode Magnitude Plot')
plt.xlabel('Frequency [Hz]')
plt.ylabel('Magnitude [dB]')
plt.xlim(1, 20000)
plt.ylim(-50, 10)
plt.grid()
plt.show()