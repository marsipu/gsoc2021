# ToDo
###### (sorted by priority)

## Benchmark-Utility
- [X] FPS Horizontal Scrolling
- [X] FPS Vertical Scrolling
- [X] Time Zooming (X-Axis)
- [X] Time Zooming (Y-Axis)

## Basic Features
- [X] Multiple Line-Plots
- [X] X-Axes
- [X] Y-Axes (with channel-names)
- [X] Vertical Scrolling (Only load shown channels in ViewBox)
- [X] Horizontal Scrollbar
- [X] Vertical Scrollbar
- [X] changing scaling
- [X] channel-type colors
- [X] Annotation-Management
- [ ] Adapt Tests
- [X] Preload in Thread (with max. RAM-Space Parameter in config)
- [X] Overview-Bar
- [ ] Event Lines
- [ ] Scale-Bars/Legends
- [X] Zoom Duration/N-Channels
- [X] Vertical Line
- [X] Mark Channels (including channel-label)
- [X] Area Selection

## Additional (after GSoC)
- [ ] Applying projections
- [X] Butterfly-Mode
- [ ] Channel-Clipping
- [ ] adaption to Epochs
- [ ] Per-channel-annotation
- [ ] Group channels (group_by-parameter)
- [ ] Selection-Figure

## Application Configuration
- [X] Entry point for application (solved with python -m [...])

## Performance
- [X] Downsampling-test (with artificial peak-file, no omission of peaks)
- [X] Profiling/Optimizing current code (range-update, LineItem-Initialization)
- [X] Compare sequential line-update or direct signal-connection on xrange-change
- [X] Downsampling as in hdf5-example
- [ ] Use numba (and other ideas as suggested in [#1478](https://github.com/pyqtgraph/pyqtgraph/issues/1478) from pyqtgraph)

## Annotations
- [X] Edit description/color of single annotation

## User Interaction
- [X] Arrow-Keys for left-right-movement
- [X] Fix Arrow on MacOs
- [ ] Right-Click Dragging for scaling
- [ ] Pinching for zooming

## Codestyle
- [X] line-width 79 characters

## Advanced Features
- [ ] custom colors for annotations (like in event-colors, needs to be adapted in mne-python)
- [X] OpenGL (optional, but not on Windws)
- [X] Tooltip/Crosshair at cursor which shows time/value under cursor-tip (prerequisite: handle different channel-scales)
- [X] OverviewBar (GFP, zscore, etc.)
- [ ] Dark Mode (preferably with parameter accepting dict for colors to be adjusted by user)
- [ ] Interactive Filter-Settings
- [ ]
