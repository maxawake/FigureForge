import matplotlib.pyplot as plt

import figureforge as FF

fig, ax = plt.subplots()

ax.plot([1, 2, 3, 4], [1, 4, 2, 3])

fig = FF.run(fig)

plt.show()
