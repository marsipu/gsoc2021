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
- [ ] channel-type colors
- [ ] Annotation-Management
- [ ] Event Lines
- [ ] Overview-Bar
- [ ] adaption to Epochs
- [ ] Per-channel-annotation
- [X] Zoom Duration/N-Channels
- [X] Vertical Line
- [X] Mark Channels (including channel-label)
- [X] Area Selection


## Performance
- [ ] Profiling/Optimizing current code (range-update, LineItem-Initialization)
- [ ] Downsampling with min/max
- [ ] Downsampling as in hdf5-example
- [ ] Downsampling-test (with artificial peak-file, no omission of peaks)


## User Interaction
- [X] Arrow-Keys for left-right-movement

## Advanced Features
- [ ] change distance between channels dynamically (up to zero==butterfly)
- [X] OpenGL (optional, but not on Windws)
- [ ] Tooltip/Crosshair at cursor which shows time/value under cursor-tip (prerequisite: handle different channel-scales)

## Outlook
- [ ] OverviewBar (GFP, zscore, etc.)