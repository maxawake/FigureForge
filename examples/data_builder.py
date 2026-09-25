"""Run with: uv run python examples/data_builder.py."""

import numpy as np
import figureforge


def main():
    time = np.linspace(0, 2 * np.pi, 150)
    data = {
        'time': time,
        'signal': np.sin(time),
        'reference': np.cos(time),
        'uncertainty': np.full_like(time, 0.15),
        'image': np.outer(np.sin(time[::5]), np.cos(time[::5])),
    }
    figure = figureforge.run(data)
    figure.savefig('figure.png', dpi=200)


if __name__ == '__main__':
    main()
