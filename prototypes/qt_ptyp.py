"""
This is a prototype of a Raw-Plot based just on the Plotting-Capabilities of PyQt5/PySide2.
It was originally created by Clemens Brunner (https://github.com/cbrnr).
"""
import sys
from collections import OrderedDict

from PyQt5.QtCore import QRectF
from PyQt5.QtWidgets import QGraphicsItem, QWidget
from qtpy.QtWidgets import (QApplication, QGraphicsPathItem, QGraphicsScene,
                            QGraphicsView, QOpenGLWidget)
from qtpy.QtGui import QPainterPath, QColor, QSurfaceFormat, QPainter, QPen
from qtpy.QtCore import Qt
import numpy as np
import mne


class Line(QGraphicsPathItem):
    def __init__(self, data, times, ch_name, ypos, sfreq, ds,
                 all_data, isbad=False):
        super().__init__()
        self._data = data
        self._times = times
        self.ch_name = ch_name
        self.ypos = ypos
        self.sfreq = sfreq
        self.ds = ds
        self.isbad = isbad
        self.update_bad_color()

    @property
    def data(self):
        return self._data

    @data.setter
    def data(self, value):
        self._data = value

    @property
    def times(self):
        return self._times

    @times.setter
    def times(self, value):
        self._times = value

    def set_full_data(self):
        self.make_path(self.times, self.data)

    def make_path(self, x, y):
        path = QPainterPath()
        y += self.ypos
        path.moveTo(x[0], y[0])
        for point in zip(x[1:], y[1:]):
            path.lineTo(*point)
        self.setPath(path)
        self.setPos(0, self.ypos)

    def update_bad_color(self):
        if self.isbad:
            pen = QPen(QColor('k'))
        else:
            pen = QPen(QColor('r'))
        pen.setCosmetic(True)  # don't scale line width
        pen.setWidth(2)
        self.setPen(pen)

    def xrange_changed(self, xmin, xmax):
        start = max(0, int(xmin * self.sfreq))
        stop = min(len(self.data), int(xmax * self.sfreq + 1))

        visible_x = self.times[start:stop]
        visible_y = self.data[start:stop]

        if self.ds > 1:
            # Auto-Downsampling and mean method from pyqtgraph
            n = len(visible_x) // self.ds
            visible_x = visible_x[:n * self.ds].reshape(n, self.ds).mean(axis=1)
            visible_y = visible_y[:n * self.ds].reshape(n, self.ds).mean(axis=1)

        self.make_path(visible_x, visible_y)


class PyQtPtyp(QGraphicsView):
    def __init__(self, raw, data, times, duration=20, nchan=30, ds=1,
                 all_data=False, enable_cache=False, use_opengl=False):
        super().__init__()
        self.ensureVisible(0, 0, 1, 1)
        self.raw = raw
        self.data = data
        self.times = times
        self.duration = duration
        self.nchan = nchan
        self.ds = ds
        self.all_data = all_data
        self.enable_cache = enable_cache
        self.use_opengl = use_opengl

        self.lines = OrderedDict()
        self.setScene(QGraphicsScene())
        # self.setSceneRect(QRectF(0, 0, duration, nchan))
        self.fitInView(QRectF(0, 0, duration, nchan))

        if self.all_data:
            max_idx = len(self.data)
        else:
            max_idx = self.nchan

        for ch_idx, (ch_data, ch_name) in enumerate(zip(self.data[:max_idx],
                                                        self.raw.ch_names[:max_idx])):
            self.add_line(ch_idx, ch_data, ch_name)

        if not self.all_data:
            self.horizontalScrollBar().valueChanged.connect(self.xrange_changed)
            self.verticalScrollBar().valueChanged.connect(self.yrange_changed)

        if self.use_opengl:
            # enable OpenGL
            opengl = QOpenGLWidget()
            fmt = QSurfaceFormat()
            fmt.setSamples(4)  # enable antialiasing with OpenGL
            opengl.setFormat(fmt)
            self.setViewport(opengl)

    def add_line(self, ch_idx, ch_data, ch_name):
        ypos = ch_idx + 1
        item = Line(data=ch_data, times=self.times, ch_name=ch_name, ypos=ypos,
                    sfreq=self.raw.info['sfreq'], ds=self.ds, all_data=self.all_data,
                    isbad=ch_name in self.raw.info['bads'])
        self.lines[ch_name] = (item, ypos)
        if self.enable_cache:
            item.setCacheMode(QGraphicsItem.DeviceCoordinateCache)

        if self.all_data:
            item.set_full_data()
        else:
            xmin = self.horizontalScrollBar().value()
            xmax = xmin + self.duration
            item.xrange_changed(xmin, xmax)
            self.nchan = len(self.lines)

        self.scene().addItem(item)

    def remove_line(self, ch_name):
        self.scene().removeItem(self.lines[ch_name][0])
        self.lines.pop(ch_name)
        self.nchan = len(self.lines)

    def xrange_changed(self, xmin):
        xmax = xmin + self.duration
        for ch_name in self.lines:
            line = self.lines[ch_name][0]
            line.xrange_changed(xmin, xmax)

    def yrange_changed(self, ymin):
        ymax = ymin + self.nchan
        remove_lines = [k for k in self.lines
                        if self.lines[k][1] <= ymin
                        or self.lines[k][1] >= ymax - 1]
        for ch_name in remove_lines:
            self.remove_line(ch_name)

        if len(self.lines) > 0:
            min_ch_idx = min([v[1] for v in self.lines.values()]) - 1
            ymin_ch_idx = ymin
            for idx in reversed(range(ymin_ch_idx, min_ch_idx)):
                ch_name = self.raw.ch_names[idx]
                self.add_line(idx, self.data[idx], ch_name)
                self.lines.move_to_end(ch_name, last=False)

            max_ch_idx = max([v[1] for v in self.lines.values()])
            ymax_ch_idx = ymax - 2
            for idx in range(max_ch_idx, ymax_ch_idx):
                ch_name = self.raw.ch_names[idx]
                self.add_line(idx, self.data[idx], ch_name)
                self.lines.move_to_end(ch_name, last=True)
        else:
            for idx in range(ymin, ymax):
                ch_name = self.raw.ch_names[idx]
                self.add_line(idx, self.data[idx], ch_name)
                self.lines.move_to_end(ch_name, last=True)

    def hscroll(self, step):
        new_right = self.sceneRect().right() + step
        if 0 <= new_right <= self.xmax:
            new_rect = self.sceneRect().moveRight(new_right)
            self.setSceneRect(new_rect)

    def infini_hscroll(self, step, parent):
        if parent.n_bm % (int(self.xmax / step) - self.duration) == 0:
            self._hscroll_dir *= -1
        step *= self._hscroll_dir
        self.hscroll(step)

    def vscroll(self, step):
        new_top = self.sceneRect().top() + step
        if 0 <= new_top <= self.ymax:
            new_rect = self.sceneRect().moveTop(new_top)
            self.setSceneRect(new_rect)

    def infini_vscroll(self, step, parent):
        if parent.n_bm % (int(self.ymax / step) - self.nchan) == 0:
            self._vscroll_dir *= -1
        step *= self._vscroll_dir
        self.vscroll(step)

    def change_duration(self, step):
        width = self.sceneRect().width()
        new_width = width + step

        self.duration = new_width
        new_rect = self.sceneRect().setWidth(new_width)
        self.setSceneRect(new_rect)

    def change_nchan(self, step):
        height = self.sceneRect().height()
        new_height = height + step

        self.nchan = new_height
        new_rect = self.sceneRect().setHeight(new_height)
        self.setSceneRect(new_rect)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Plus:  # zoom in
            self.scale(1.25, 1.25)
        elif event.key() == Qt.Key_Minus:  # zoom out
            self.scale(0.75, 0.75)
        elif event.key() == Qt.Key_Left:
            self.translate(-100, 0)
        elif event.key() == Qt.Key_Right:
            self.translate(100, 0)
        elif event.key() == Qt.Key_Up:
            self.translate(0, -100)
        elif event.key() == Qt.Key_Down:
            self.translate(0, 100)
        elif event.key() == Qt.Key_Escape:
            self.close()