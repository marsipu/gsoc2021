import sys
import numpy as np
from PyQt5.QtWidgets import QApplication
import pyqtgraph as pg
from pyqtgraph import PlotCurveItem
import mne


class RawCurveItem(PlotCurveItem):
    def __init__(self, raw=None, *args, **kwargs):
        self._raw = raw
        self.limit = 10000  # maximum number of samples to be plotted
        super().__init__(*args, **kwargs)

    @property
    def raw(self):
        return self._raw

    @raw.setter
    def raw(self, value):
        self._raw = value
        self.viewRangeChanged()

    def viewRangeChanged(self):
        viewbox = self.getViewBox()
        if viewbox is None:
            return
        xrange = viewbox.viewRange()[0]
        start = max(0, int(xrange[0]))
        stop = min(len(self.raw), int(xrange[1] + 1))

        ds = int((stop - start) / self.limit) + 1
        print(ds)
        if ds == 1:
            visible = self.raw[start:stop]
            scale = 1
        else:
            # Here convert data into a down-sampled array suitable for visualizing.
            # Must do this piecewise to limit memory usage.
            samples = 1 + ((stop-start) // ds)
            visible = np.zeros(samples*2, dtype=self.raw.dtype)
            sourcePtr = start
            targetPtr = 0

            # read data in chunks of ~1M samples
            chunkSize = (1000000//ds) * ds
            while sourcePtr < stop-1:
                chunk = self.raw[sourcePtr:min(stop,sourcePtr+chunkSize)]
                sourcePtr += len(chunk)

                # reshape chunk to be integral multiple of ds
     s           chunk = chunk[:(len(chunk)//ds) * ds].reshape(len(chunk)//ds, ds)

                # compute max and min
                chunkMax = chunk.max(axis=1)
                chunkMin = chunk.min(axis=1)

                # interleave min and max into plot data to preserve envelope shape
                visible[targetPtr:targetPtr+chunk.shape[0]*2:2] = chunkMin
                visible[1+targetPtr:1+targetPtr+chunk.shape[0]*2:2] = chunkMax
                targetPtr += chunk.shape[0]*2

            visible = visible[:targetPtr]
            scale = ds * 0.5
        self.setData(visible)
        self.setPos(start, 0)
        self.resetTransform()
        self.scale(scale, 1)


# load data
from mne.datasets import sample
data_path = sample.data_path()
raw_fname = data_path + '/MEG/sample/sample_audvis_raw.fif'

raw = mne.io.read_raw_fif(raw_fname, preload=True)
raw.filter(1, None)
data = raw.get_data()

# create window with empty layout
app = QApplication(sys.argv)
pg.setConfigOptions(background="w", foreground="k", antialias=True)
win = pg.GraphicsView()
win.resize(1000, 800)
layout = pg.GraphicsLayout()
layout.setSpacing(0)
win.setCentralItem(layout)
win.show()

plots = []
for ch in range(4):  # add plots in rows
    p = layout.addPlot(row=ch, col=0, enableMenu=False)
    p.setXRange(0, 2000)
    p.setLimits(xMin=0, xMax=data.shape[1])
    curve = RawCurveItem(data[ch] * 1e6)
    curve.setPen("k")
    p.addItem(curve)
    plots.append(p)
for ch in range(4 - 1):  # link axes
    plots[ch].setXLink(plots[ch + 1])
    plots[ch].setYLink(plots[ch + 1])
    plots[ch].getAxis("bottom").setStyle(showValues=False)
    plots[ch].getAxis("bottom").hide()

layout.setSpacing(0)

sys.exit(app.exec())
