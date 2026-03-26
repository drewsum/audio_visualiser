import numpy as np
import matplotlib.pyplot as plt
import scipy.signal as signal # type: ignore

# Example: A transfer function H(s)
num1_lp = np.array([-2.2575116442451E+14])
den1_lp = np.array([1, 121580.12765223, 7027576946.629, 2.0790954013934E+14])
num1_hp = np.array([-0.96961861667744, 0, 0, 0])
den1_hp = np.array([1, 140466.61091731, 9957188452.7278, 3.5337122805367E+14])
# Multiply the transfer functions by convolving their coefficients
num1_total = np.convolve(num1_lp, num1_hp)
den1_total = np.convolve(den1_lp, den1_hp)
# Create the resulting transfer function object
system1 = signal.TransferFunction(num1_total, den1_total)

# Example: A transfer function H(s)
num2_lp = np.array([-225751164424.51])
den2_lp = np.array([1, 12158.012765223, 70275769.46629, 207909540139.34])
num2_hp = np.array([-0.96961861667744, 0, 0, 0])
den2_hp = np.array([1, 14046.661091731, 99571884.527278, 353371228053.67])
# Multiply the transfer functions by convolving their coefficients
num2_total = np.convolve(num2_lp, num2_hp)
den2_total = np.convolve(den2_lp, den2_hp)
# Create the resulting transfer function object
system2 = signal.TransferFunction(num2_total, den2_total)

w = np.logspace(2, 7, num=1000) # Frequencies in rad/s

# Calculate the frequency response
w1, mag1, phase1 = signal.bode(system1, w=w)
# Calculate the frequency response
w2, mag2, phase2 = signal.bode(system2, w=w)

f = w / (2 * np.pi)

# Plot the response
plt.figure()
plt.semilogx(f, mag1)    # Bode magnitude plot
plt.semilogx(f, mag2)    # Bode magnitude plot
plt.title('Bode Magnitude Plot')
plt.xlabel('Frequency [Hz]')
plt.ylabel('Magnitude [dB]')
plt.ylim(-50, 10)
plt.grid()
plt.show()