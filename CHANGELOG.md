# Week 6
## Tuesday
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