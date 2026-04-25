import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

x = np.linspace(-6 * np.pi, 6 * np.pi, 1000)
y_cos = np.cos(x)
y_sin = np.sin(x)

fig, ax = plt.subplots(figsize=(10, 6))
ax.plot(x, y_cos, label="cos(x)", color="#6C3FC5", linewidth=2)
ax.plot(x, y_sin, label="sin(x)", color="#B362FF", linewidth=2, linestyle="--")
ax.set_xlabel("x")
ax.set_ylabel("y")
ax.set_title("sin(x) and cos(x) from -6π to 6π")
ax.legend()
ax.grid(True, alpha=0.3)
ax.axhline(y=0, color="gray", linewidth=0.5)
ax.axvline(x=0, color="gray", linewidth=0.5)

output_path = "/home/thomas/src/crow-ai/crow-cli/sandbox/crow-test/graph.png"
fig.savefig(output_path, dpi=150, bbox_inches="tight")
plt.close()
print(f"Saved to {output_path}")
