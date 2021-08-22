# Final Report for Google Summer of Code 2021
## MNE-Python: Enhancing Performance of Signal Browsing using PyQt

### Summary
#### Task
The aim of this [project](https://blogs.python-gsoc.org/media/proposals/GSoC2021_Application_Schulz.pdf) was to supply an additional backend for the visualization
of 2D-Data in the data-browser of MNE-Python. The current backend matplotlib sets
limits in performance, the addition of features and a native 
appearance. A new backend on the base of [(Py)Qt](https://riverbankcomputing.com/software/pyqt/intro) was supposed to improve the 
data-browser in regard of the afformentioned aspects.

#### Backend-Selection
At the beginning of the project, I experimented with several prototypes supplied
by the mentors and compared peformance and accessibility (from a developers 
perspective) of multiple backends, including [pyqtgraph](https://github.com/pyqtgraph/pyqtgraph),
[pyqwt](https://github.com/PyQwt/PyQwt), (custom) pyqt,
[vispy](https://github.com/vispy/vispy) and [vtk](https://vtk.org/). 
Quickly pyqtgraph emerged as being the most accessible solution
for our needs, while sustaining a lot of the performance of a native pyqt 
solution. Especially in the beginning the well documented package facilitated
my understanding of the Graphics-View-Framework from Qt a lot. The package
often provided top-level-classes for the features we needed, which I just had
to customize then. And multiple potential pitfalls have been already taken 
care of. 
Thanks a lot [@pyqtgraph-developers](https://github.com/pyqtgraph/pyqtgraph/graphs/contributors)!

#### Basic Features
After it had been clear that I was focusing on pyqtgraph, I worked on implementing
the features the matplotlib-backend provides:

- browsing through 2-dimensional data horizontally and vertically
- increase/decrease shown duration and number of channels
- time on x-axis, channel-names on y-axis
- datetime on x-axis (which [I have implemented for matplotlib](https://github.com/mne-tools/mne-python/pull/9419) before)
- mark bad-channels (click trace of ch-name)
- add/remove/edit annotations
- keyboard-shortcuts
- vertical line
- overview-bar
- butterfly-mode
- zen-mode

#### Additional Features
Along the way, I implemented a few new features:
- extended organization of annotations (with custom colors, saving these will be subject of a future PR)
- a crosshair (press x)
- smooth-scrolling with trackpad (horizontally and vertically)
- display channel-wise zscores on the Overview-Bar (`overview_mode=zscore`)


#### Performance
The usage of the C++-based Qt-library itself brought a major perfomance increase
in comparison to the matplotlib-backend. To maximize this increase, I often revised
the way items are drawn and updated and searched in the pyqtgraph-discussions
for ways to improve performance. One I found was the usage of OpenGL with pyopengl.
Connected to this feature was a bug I found where an antialiasing-parameter
wasn't passed to PlotCurveItems which I fixed in this [PR](https://github.com/pyqtgraph/pyqtgraph/pull/1932).
Another performance increase could be achieved by preloading the data. This would
normally scale startup time with the file-size, but to prevent thisI implemented the
(pythonic) parallel loading in a separate thread to keep startup-time low.

- creation of a benchmark-utility to compare and visualize the effect of different performance inflicting parameters.
- optimized drawing and update of RawTraceItems
- downsampling (customized methods originally from pyqtgraph)
- usage of OpenGL (implemented with pyopengl by pyqtgraph)
- preloading of data (in a separate thread to reduce startup-time)

#### Refactoring of MPL-Backend and Tests
Following my mentors advice I started early with refactoring the matplotlib-backend
to facilitate the later side-by-side integration of matplotlib and pyqtgraph.
I refactored all methods from the matplotlib-backend which were backend-independent
into a new Base-Class for both backends called `BrowserBase`.
To make the existing tests passable by both backends, I created abstract methods
which forced an implementation of the respective backend-specific method in each backend.
The additional functions set/get/use-backend provided a new interface for determining
the used backend.
A [PR](https://github.com/mne-tools/mne-python/pull/9596) containing these changes could aready be merged.

#### Adaption of pyqtgraph-browser to BrowserBase and Tests
Since for the first half of GSoC I have worked with a pyqtgraph-browser-prototype
with rudimentary data-loading and -processing, the adaption of this rudimentary
structure to the full framework the then refactored BrowserBase provided was 
another big task. Furthermore, the aforementioned abstract methods for testing
had to be provided for the pyqtgraph-backend.

#### Outcome and ToDos left
The outcome of this project is this open [WIP-PR](https://github.com/mne-tools/mne-python/pull/9687) 
containing the new backend and the above-mentioned related PR's.
To reach feature-parity with the matplotlib-backend, the following features are still left to be implemented:
- Epochs
- Event-Lines
- Scale-Bars
- Channel-Clipping
- `group_by`-parameter

And there are still tests left which need to be adapted to pass with pyqtgraph.

I listed the ToDo's left together with ideas for feature-expansion in [this issue](https://github.com/mne-tools/mne-python/issues/9686)

To follow my development process in retrospective, you can look at the daily [changelog](CHANGELOG.md)
and the [weekly blogs](https://blogs.python-gsoc.org/en/marsipus-blog/) I wrote.

#### Run the new backend
To test the functionality of the new backend, you need to install the following requirments via pip in a python environment:
```
mne
PyQt5
pyqtgraph
pyopengl  # optional, but recommended for higher performance
```

And to run, you can run the following example code:
```python
import mne
import os
import numpy as np

from mne.viz._figure import use_browser_backend

sample_data_folder = mne.datasets.sample.data_path()
sample_data_raw_file = os.path.join(sample_data_folder, 'MEG', 'sample',
                                    'sample_audvis_raw.fif')
raw = mne.io.read_raw(sample_data_raw_file)

with use_browser_backend('pyqtgraph'):
    annot = raw.annotations
    annot.onset = np.arange(2, 8, 2) + raw.first_time
    annot.duration = np.repeat(1, len(annot.onset))
    annot.description = np.asarray(['Test1', 'Test2', 'Test3'])

    raw.plot(block=True)
```
