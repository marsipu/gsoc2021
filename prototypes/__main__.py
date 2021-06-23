import sys

from PyQt5.QtWidgets import QApplication
from pyqtgraph import mkQApp

from prototypes.benchmark_utils import BenchmarkWindow

def main():
    app = mkQApp()
    benchmark_win = BenchmarkWindow()
    benchmark_win.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()