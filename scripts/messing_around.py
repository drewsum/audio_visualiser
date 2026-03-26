import numpy as np
import matplotlib.pyplot as plt
import scipy.signal as signal # type: ignore

# Example: A transfer function H(s) = (s + 1) / (s^2 + 2s + 1)
# Numerator coefficients [1, 1] (for 1*s^1 + 1*s^0)
num_lp = np.array([342794460441.52])
# Denominator coefficients [1, 2, 1] (for 1*s^2 + 2*s^1 + 1*s^0)
den_lp = np.array([1, 116550.11655012, 342794460441.52])

num_hp = np.array([1, 0, 0])
den_hp = np.array([1, 13333.333333333, 4444444444.4444])

# Multiply the transfer functions by convolving their coefficients
num_total = np.convolve(num_lp, num_hp)
den_total = np.convolve(den_lp, den_hp)

# Create the resulting transfer function object
system = signal.TransferFunction(num_total, den_total)

# Calculate the frequency response
w, mag, phase = signal.bode(system)

f = w / (2 * np.pi)

# Plot the response
plt.figure()
plt.semilogx(f, mag)    # Bode magnitude plot
plt.title('Bode Magnitude Plot')
plt.xlabel('Frequency [Hz]')
plt.ylabel('Magnitude [dB]')
plt.grid()
plt.show()