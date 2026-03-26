import numpy as np
import matplotlib.pyplot as plt
import scipy.signal as signal # type: ignore

# Example: A transfer function H(s) = (s + 1) / (s^2 + 2s + 1)
# Numerator coefficients [1, 1] (for 1*s^1 + 1*s^0)
num = np.array([1, 1])
# Denominator coefficients [1, 2, 1] (for 1*s^2 + 2*s^1 + 1*s^0)
den = np.array([1, 2, 1])

# Create the LTI system (transfer function representation)
system = signal.TransferFunction(num, den)

# Calculate the step response
t, y = signal.step(system)

# Plot the response
plt.plot(t, y)
plt.xlabel('Time (s)')
plt.ylabel('Amplitude')
plt.title('Step Response')
plt.grid()
plt.show()