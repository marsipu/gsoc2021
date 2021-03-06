# Week 11
## Friday, 2021-08-20
- fixed bugs (overview-bar, mouseDrag, annotations)

## Thursday, 2021-08-19
- preload data in separate thread
- overview-bar with zscore-mode

## Wednesday, 2021-08-18
- finally!! made fake-clicks work in pyqtgraph
- adapted/refactored test_plot_raw_traces to pass for pyqtgraph
- added butterfly- and zen-mode

## Tuesday, 2021-08-17
- made progress with the fake-clicks
- introduced crosshair to pyqtgraph-backend for troubleshooting fake-clicks

## Monday, 2021-08-16
- tried to make fake-clicks work with pyqtgraph-backend (got stuck, asked mentors for help)

# Week 10
## Friday, 2021-08-13
- worked on fake-clicks in pyqtgraph-backend
- WIP test_plot_raw_traces

## Thursday, 2021-08-12
- added matplotlib to benchmark-utility
- added Epochs and ICA to benchmark-utility
- WIP adaption of pyqtgraph-backend to epochs

## Wednesday, 2021-08-11
- fixed more bugs in pyqtgraph-prototyp and preloading-behaviour
- adapted benchmark to integrated pyqtgraph-prototype
- added startup-time to benchmark
- examined effect of preload on performance

## Tuesday, 2021-08-10
- fixed bugs from adaption of pyqtgraph-prototyp
- improved performance in vertical scrolling by reusing existing 
  RawTraceItems
- dissolved RawPlot into Main-Class for less nesting

## Monday, 2021-08-09
- continued WIP of adapation of pyqtgraph-prototyp (updating traces, 
  downsampling, local vs. global preprocessing)

# Week 9
## Friday, 2021-08-06
- worked on adaption and generalization of data-loading in pyqtgraph and 
  matplotlib

## Thursday, 2021-08-05
- worked on adaption of PyQtGraph-Prototype to BrowserBase

## Wednesday, 2021-08-04
- worked on feedback on [Refactoring PR](https://github.com/mne-tools/mne-python/pull/9596)
- started adaption of PyQtGraph-Prototype to BrowserBase

## Tuesday, 2021-08-03
- continued work on [Refactoring PR](https://github.com/mne-tools/mne-python/pull/9596):
  - fix failing tests
  - refactored tests in `mne.viz.tests.test_epochs.py` and `mne.viz.tests.test_ica.py`

## Monday, 2021-08-02
- continued work on [Refactoring PR](https://github.com/mne-tools/mne-python/pull/9596):
  - implemented feedback of @drammock
  - refactored other tests in `mne.viz.tests.test_raw.py`

# Week 8
## Friday, 2021-07-30
- worked further on [Refactoring PR](https://github.com/mne-tools/mne-python/pull/9596):
  - created abstract-methods for test-interaction
  - started with refactoring of tests in `mne.viz.tests.test_raw.py`

## Thursday, 2021-07-29
- worked on [PR](https://github.com/pyqtgraph/pyqtgraph/pull/1932) in pyqtgraph to make OpenGl-AA optional
- added use/set/get-structure for browser-backend

## Wednesday, 2021-07-28
- refactored the RawIO of test_raw.py
- prepared browser_backend-fixture

## Tuesday, 2021-07-27
- unscheduled events in my laboratory required my attention.

## Monday, 2021-07-26
- opened [issue](https://github.com/pyqtgraph/pyqtgraph/issues/1926) and 
  [PR](https://github.com/pyqtgraph/pyqtgraph/pull/1925) for pyqtgraph
- added check_nan as parameter to test influence of performance of the 
  parameters connect and SkipFiniteCheck in setData
- refreshed knowledge about fixtures and generators

# Week 7
## Friday, 2021-07-23
- worked on adaption of pyqtgraph-prototype to BrowserBase
- nothing else due to some unscheduled events.

## Thursday, 2021-07-22
- continued work on refactoring backend-independent parts of MPL-Class into 
  BrowserBase

## Wednesday, 2021-07-21
- continued work on MNE-Python integration

## Tuesday, 2021-07-20
- prepared preliminal integration of PyQtGraph-Prototype into MNE-Python
  to make feature integration as Epochs etc. easier

## Monday, 2021-07-19
- refactored pyqtgraph-prototype to fit better into envisioned 
  MNEDataBrowser-MetaClass
- removed Annoation-Controller (too verbose)

# Week 6
## Friday, 2021-07-16
- worked on touch/gesture-control
- started with [abstract base-class](https://github.com/marsipu/mne-python/tree/rawplot_refactor)

## Thursday, 2021-07-15
- worked into how to abstract existing matplotlib-backend
- added scaling

## Wednesday, 2021-07-14
- added tsteps_per_window and fixed related bugs
- added channel-colors

## Tuesday, 2021-07-13
- fix bugs for ctrl-modifier on MacOS, imports, annotations
- compared xrange-signal-connection (no big differences)
- added downsampling-cache

## Monday, 2021-07-12
- fixed some annotation-bugs
- moved auto-downsampling away from PlotCurveItems
- fixed color-bug for benchmark results
- fixed bugs at scroll-boundaries
- added downsampling-test

# Week 5
## Friday, 2021-07-09
- finish annotation-managemet

## Thursday, 2021-07-08
- Fixed bugs in scrolling-behaviour
- added more downsampling from pyqtgraph

## Wednesday, 2021-07-07
- making dragging of Vline-label work too
- simplify yrange-update (to prepare easier scrolling-troubleshooting)

## Tuesday, 2021-07-06
- refactored pyqtgraph-prototype to have only one main (the Top-Level Class, 
  where I shifted most of the attributes and methods from RawPlot not directly 
  related to the LinePlot for less confusion)

## Monday, 2021-07-05
- working with ephyviewer and hdf5-example

# Week 4
## Friday, 2021-07-02
- regions updating while dragging
- started work on annotation-manager

## Thursday, 2021-07-01
- added auto-downsampling
- added vline

## Wednesday, 2021-06-30
- implemented annotations

## Tuesday, 2021-06-29
- tried to fix OpenGL-issue
- started adding annotations

## Monday, 2021-06-28
- fix benchmark-bugs
- fix OpenGl-Problem
- add keyboard-shortcuts

# Week 3
## Friday, 2021-06-24
- add all_data parameter to compare QScene-Scrolling performance
- add qt-prototype to investigate OpenGL-Issue and compare

## Thursday, 2021-06-24
- fix scrollbar-issues
- add scalings for multiple types
- remove vspace-parameter

## Wednesday, 2021-06-23
- improve performance of horizontal scrollbar
- add vertical scrollbar
- fix benchmarks

## Tuesday, 2021-06-22
- improve bad-channel-selection (color of ch_name and clicking on ch_name)
- add horizontal scrollbar

## Monday, 2021-06-21
- add clock-time to X-Axis
- list channels from the top
- implement basic bad-channel-selection

# Week 2
## Friday, 2021-06-18
- add channel-names to Y-Axis

## Thursday, 2021-06-17
- add benchmarks for vertical scrolling, changing channel-count, changing duration

## Wednesday, 2021-06-16
- transition to lower-level use of PlotItem
- implementation of y/channel-scrolling

## Tuesday, 2021-06-15
- fix bugs in benchmark_utils and pyqtgraph_ptyp

## Monday, 2021-06-14
- add queue-functionality to compare different parameter-settings
- visualization of benchmark-results with pyqtgraph
- wrote [blog-entry](https://blogs.python-gsoc.org/en/marsipus-blog/blog-week-1-07-06-12-06/)

# Week 1

## Friday, 2021-06-11
- studied pyqtgraph source-code (children of QGraphicsItem, QGraphicsView)
- fixed a few bugs in pyqtgraph-prototype

## Thursday, 2021-06-10
- improved pyqtgraph-prototype
- added first benchmark (hscroll)

## Wednesday, 2021-06-09
- worked on PR #9419 (still left from Community-Bonding)
- worked on pyqtgraph-prototype to include all PlotCurveItems in one plot
- worked on PR #9444

## Tuesday, 2021-06-08
- studied source-code of pyqtgraph (especially downsample-method)
- started benchmark_utils.py to unify testing of multiple backends
- started adaption of pyqtgraph-prototype

## Monday, 2021-06-07
- forked & studied the implementation of [sigviewer](https://github.com/cbrnr/sigviewer)
- created TODO.md for prototypes
- wrote first [blog-entry](https://blogs.python-gsoc.org/en/marsipus-blog/weekly-check-in-community-bonding-period-17-05-06-06/)