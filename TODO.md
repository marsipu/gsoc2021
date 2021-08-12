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
- [ ] Preload in Thread (with max. RAM-Space Parameter in config)
- [ ] Overview-Bar
- [ ] Event Lines
- [ ] Scale-Bars/Legends
- [ ] Channel-Clipping
- [X] Zoom Duration/N-Channels
- [X] Vertical Line
- [X] Mark Channels (including channel-label)
- [X] Area Selection

## Additional (after GSoC)
- [ ] Applying projections
- [ ] Butterfly-Mode
- [ ] adaption to Epochs
- [ ] Per-channel-annotation
- [ ] Group channels (group_by-parameter)
- [ ] Selection-Figure

## Application Configuration
- [X] Entry point for application (solved with python -m [...])

## Performance
- [X] Downsampling-test (with artificial peak-file, no omission of peaks)
- [ ] Profiling/Optimizing current code (range-update, LineItem-Initialization)
- [X] Compare sequential line-update or direct signal-connection on xrange-change
- [X] Downsampling as in hdf5-example
- [ ] Use numba (and other ideas as suggested in [#1478](https://github.com/pyqtgraph/pyqtgraph/issues/1478) from pyqtgraph)

## Annotations
- [ ] Edit description/color of single annotation

## User Interaction
- [X] Arrow-Keys for left-right-movement
- [X] Fix Arrow on MacOs
- [ ] Right-Click Dragging for scaling
- [ ] Pinching for zooming

## Codestyle
- [ ] line-width 79 characters

## Advanced Features
- [ ] change distance between channels dynamically (up to zero==butterfly)
- [ ] custom colors for annotations (like in event-colors)
- [X] OpenGL (optional, but not on Windws)
- [ ] Tooltip/Crosshair at cursor which shows time/value under cursor-tip (prerequisite: handle different channel-scales)
- [ ] OverviewBar (GFP, zscore, etc.)
- [ ] Dark Mode
- [ ] Interactive Filter-Settings
