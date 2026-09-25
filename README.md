<p align="center"> <img width="30%" src="./figureforge/resources/assets/logo_color_text.png"> </p>

A Python GUI application for interactive creation and editing of matplotlib figures.

## Features
- Edit matplotlib figures via a graphical interface.
  - Adjust text labels, size, fonts, etc.
  - Change colors of lines, text, symbols, etc.
  - Adjust size of markers, lines
  - And more!
- [Save figures](htthttps://github.com/nogula/figureforge/wiki/FAQ-&-Troubleshooting#how-does-figureforge-save-figure-data) to a pickle file for use in other Python projects or to share (and load figures from a pickle file, too!).
- Use [custom plugins](https://github.com/nogula/figureforge/wiki/Plugins) to automate figure styling.

![](https://raw.githubusercontent.com/nogula/figureforge/main/figureforge/resources/assets/demo.png)

## Installation

1. Open a terminal or command prompt.
2. Optionally, create a virtual environment.
3. Run the following command to install figureforge:

    ```
    pip install figureforge
    ```
    _You may need to uninstall figureforge before upgrading._
4. Start figureforge from the terminal:
    ```
    figureforge
    ```
    or from within a script:
   ```
   import matplotlib.pyplot as plt
   import figureforge

   fig, ax = plt.subplots()
   ax.plot([1,2,3,4],[1,4,9,16])

   # Do edits with figureforge...
   fig = figureforge.run(fig)
   # Continue your script after figureforge closes...
   ```

## Help
The documentation for figureforge is available on the project's [wiki](https://github.com/nogula/figureforge/wiki) -- it is still a work in progress, but in the meantime you might find the [FAQ & Troubleshooting](https://github.com/nogula/figureforge/wiki/FAQ-&-Troubleshooting) page helpful. Consider also creating a [new issue](https://github.com/nogula/figureforge/issues), or ask a question in the [discussions](https://github.com/nogula/figureforge/discussions/1).

## Contributing
Obviously, figureforge is still early in development. Correspondingly, there are many opportunities to implement features and fix bugs. If you want to pitch in, you are welcome to fork the project and make a pull request.

Truth be told, I am an aerospace engineer and not a software developer; I don't know how to develop professional software, but am doing my best - especially because figureforge is solving one of my own problems. If you would like to contribute, I would be grateful. There is no formal development philosophy: I just recently learned that git tags are a thing. The closest thing to a development roadmap is this Kanban board, granted, these features are to some extent aspirational: [figureforge Project](https://github.com/users/nogula/projects/3/views/1).

## Acknowledgements
figureforge is possible only because of the open source technologies and resources from which figureforge stands on shoulders. Specifically, I wish to thank:
- The developers of [matplotlib](https://matplotlib.org/) who are responsible for the very foundation of this project.
- The GUI framework for figureforge is the Qt platform, specifically [PySide6](https://pypi.org/project/PySide6/).
- The menu [icons](https://fonts.google.com/icons) used in figureforge were made by Google.

## See Also
A unique function of figureforge is its ability to work on matplotlib figures as part of any Python workflow. However, if you are looking for something more polished and are not so concerned with the serialization/data format of your figure, you might find the following projects of interest.
- [Veusz](https://veusz.github.io/) is a scientific plotting and graphing program with a graphical user interface, designed to produce publication-ready 2D and 3D plots.
- [LabPlot](https://labplot.kde.org/) open source and cross-platform Data Visualization and Analysis software accessible to everyone.
