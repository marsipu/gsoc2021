import sys

import pyqtgraph as pg

from prototypes.benchmark_utils import BenchmarkWindow


def main():
    pg.setConfigOption('enableExperimental', True)

    app = pg.mkQApp()
    benchmark_win = BenchmarkWindow()
    benchmark_win.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
