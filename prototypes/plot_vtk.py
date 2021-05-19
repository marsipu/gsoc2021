"""
This is a prototype of a Raw-Plot based on pyqtgraph.
It was originally created by Eric Larson(https://github.com/larsoner) here:
https://gist.github.com/larsoner/7acaeb67f79586975d0b07584a8fc5c9
"""
import sys

import mne
import numpy as np
import vtk
from PyQt5.QtWidgets import QApplication
from vtk.util import numpy_support
import pyvistaqt

raw = mne.io.read_raw_fif(
    mne.datasets.sample.data_path() + '/MEG/sample/sample_audvis_raw.fif')
data, times = raw[:, :]
n_points = 1000
norms = np.std(data, axis=-1, keepdims=True)
data -= np.mean(data, axis=1, keepdims=True)
norms[norms == 0] = 1
data /= norms
data += np.arange(len(data))[:, np.newaxis]

w, h = 800, 600
plotter = pyvistaqt.BackgroundPlotter(window_size=(w, h))
plotter.background_color = (1., 1., 1.)
chart = vtk.vtkChartXY()
x_axis = chart.GetAxis(1)
x_axis.SetBehavior(vtk.vtkAxis.FIXED)
y_axis = chart.GetAxis(0)
y_axis.SetBehavior(vtk.vtkAxis.FIXED)
y_axis.SetRange(-0.5, len(data) + 0.5)
chart_scene = vtk.vtkContextScene()
chart_actor = vtk.vtkContextActor()
chart_scene.AddItem(chart)
chart_actor.SetScene(chart_scene)
plotter.renderer.AddActor(chart_actor)
chart_scene.SetRenderer(plotter.renderer)
table = vtk.vtkTable()
table.SetNumberOfRows(n_points)


class Updater():
    def __init__(self):
        self.offset = 0

    def __call__(self):
        chart.ClearPlots()
        sl = slice(self.offset, self.offset + n_points)
        x = times[sl].copy()
        x_v = numpy_support.numpy_to_vtk(x)
        x_v.SetName("x")
        x_axis.SetRange(x[0], x[-1])
        table.Initialize()
        table.AddColumn(x_v)
        for pi in range(len(raw.ch_names)):
            y_v = numpy_support.numpy_to_vtk(data[pi, sl])
            y_v.SetName(str(pi))
            table.AddColumn(y_v)
            line = chart.AddPlot(vtk.vtkChart.LINE)
            line.SetInputData(table, 0, pi + 1)
            line.SetColor(0, 0, 0, 128)
            line.SetWidth(1.0)
        self.offset += 10
        if self.offset > len(times) - n_points:
            self.offset = 0
        plotter.update()

app = QApplication(sys.argv)

from PyQt5.QtCore import QTimer
timer = QTimer()
up = Updater()
timer.timeout.connect(up)
timer.start(int(round(1000 / 60)))

sys.exit(app.exec())
