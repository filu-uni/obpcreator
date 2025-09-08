# SPDX-FileCopyrightText: 2022 Freemelt AB
# SPDX-License-Identifier: Apache-2.0

"""OBP data viewer."""

# Built-in
import argparse
import dataclasses
import pathlib
import gzip
import sys
import tkinter
from tkinter import ttk

# Freemelt
from obplib import OBP_pb2 as obp

# PyPI
try:
    import matplotlib
except ModuleNotFoundError:
    sys.exit(
        "Error: matplotlib is not installed. Try:\n"
        "  $ sudo apt install python3-matplotlib\n"
        "or\n"
        "  $ python3 -m pip install matplotlib"
    )

import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure
from matplotlib.ticker import EngFormatter
from matplotlib.path import Path
import matplotlib.collections as mcoll
import numpy as np
from google.protobuf.internal.decoder import _DecodeVarint32
from matplotlib.patches import Circle

plt.style.use("dark_background")

@dataclasses.dataclass
class Data:
    paths: list
    speeds: np.ndarray
    dwell_times: np.ndarray
    spotsizes: np.ndarray
    beampowers: np.ndarray
    syncpoints: dict
    restores: np.ndarray

class TimedPoint:
    pass

def load_obp_objects(filepath):
    with open(filepath, "rb") as fh:
        data = fh.read()
    if filepath.suffix == ".gz":
        data = gzip.decompress(data)
    consumed = new_pos = 0
    while consumed < len(data):
        msg_len, new_pos = _DecodeVarint32(data, consumed)
        msg_buf = data[new_pos : new_pos + msg_len]
        consumed = new_pos + msg_len
        packet = obp.Packet()
        packet.ParseFromString(msg_buf)
        attr = packet.WhichOneof("payload")
        yield getattr(packet, attr)

def _unpack_tp(obp_objects):
    for obj in obp_objects:
        if isinstance(obj, obp.TimedPoints):
            t = 0
            for point in obj.points:
                tp = TimedPoint()
                tp.x = point.x
                tp.y = point.y
                if point.t == 0:
                    point.t = t
                tp.t = t = point.t
                tp.params = obj.params
                yield tp
        else:
            yield obj

def load_artist_data(obp_objects) -> Data:
    paths, speeds, dwell_times = [], [], []
    spotsizes, beampowers, restores = [], [], []
    syncpoints, _lastseen = {}, {}
    _restore = 0

    for obj in _unpack_tp(obp_objects):
        if isinstance(obj, (obp.Line, obp.AcceleratingLine)):
            paths.append(Path(np.array([[obj.x0, obj.y0], [obj.x1, obj.y1]]) / 1e6, (Path.MOVETO, Path.LINETO)))
            speeds.append(obj.speed / 1e6 if isinstance(obj, obp.Line) else obj.sf)
            dwell_times.append(getattr(obj.params, "dwell_time", 0))
        elif isinstance(obj, (obp.Curve, obp.AcceleratingCurve)):
            paths.append(Path(np.array([[obj.p0.x, obj.p0.y], [obj.p1.x, obj.p1.y], [obj.p2.x, obj.p2.y], [obj.p3.x, obj.p3.y]]) / 1e6, [Path.MOVETO, Path.CURVE4, Path.CURVE4, Path.CURVE4]))
            speeds.append(obj.speed / 1e6 if isinstance(obj, obp.Curve) else obj.sf)
            dwell_times.append(getattr(obj.params, "dwell_time", 0))
        elif isinstance(obj, TimedPoint):
            paths.append(Path(np.array([[obj.x - 100, obj.y], [obj.x, obj.y + 100], [obj.x + 100, obj.y], [obj.x, obj.y - 100], [obj.x - 100, obj.y], [obj.x, obj.y]]) / 1e6, (Path.MOVETO, Path.LINETO, Path.LINETO, Path.LINETO, Path.LINETO, Path.MOVETO)))
            speeds.append(0)
            dwell_times.append(obj.t / 1e6)
        elif isinstance(obj, obp.SyncPoint):
            if obj.endpoint not in syncpoints:
                syncpoints[obj.endpoint] = [0] * len(paths)
            _lastseen[obj.endpoint] = int(obj.value)
            continue
        elif isinstance(obj, obp.Restore):
            _restore = 1
            continue
        else:
            continue

        spotsizes.append(obj.params.spot_size)
        beampowers.append(obj.params.beam_power)
        for k, v in _lastseen.items():
            syncpoints[k].append(v)
        restores.append(_restore)
        _restore = 0

    for key in syncpoints:
        syncpoints[key] = np.array(syncpoints[key])

    if len(paths) == 0:
        raise Exception("no lines or curves in obp data")

    return Data(
        paths,
        np.array(speeds),
        np.array(dwell_times),
        np.array(spotsizes),
        np.array(beampowers),
        syncpoints,
        np.array(restores),
    )

class ObpFrame(ttk.Frame):
    def __init__(self, master, data, slice_size, index=None, **kwargs):
        super().__init__(master, **kwargs)
        self.data = data
        index = index if index is not None else slice_size
        self.cap = lambda i: max(0, min(len(self.data.paths) - 1, int(i)))

        index = self.cap(index)
        slice_ = slice(self.cap(index + 1 - slice_size), self.cap(index) + 1)

        fig = Figure(figsize=(9, 8), constrained_layout=True)
        ax = fig.add_subplot(111)
        ax.axhline(0, linewidth=1, zorder=0)
        ax.axvline(0, linewidth=1, zorder=0)
        ax.add_patch(Circle((0, 0), 0.04, edgecolor='white', facecolor='none'))
        ax.add_patch(Circle((0, 0), 0.05, edgecolor='grey', facecolor='none', linestyle='--'))
        ax.set_xlim([-0.05, 0.05])
        ax.set_ylim([-0.05, 0.05])
        si_meter = EngFormatter(unit="m")
        ax.xaxis.set_major_formatter(si_meter)
        ax.yaxis.set_major_formatter(si_meter)
        ax.tick_params(axis="x", labelsize=8)
        ax.tick_params(axis="y", labelsize=8)

        self.path_collection = mcoll.PathCollection(
            self.data.paths[slice_],
            facecolors="none",
            transform=ax.transData,
            cmap=plt.cm.rainbow,
            norm=plt.Normalize(vmin=0, vmax=max(self.data.speeds)),
        )
        self.path_collection.set_array(self.data.speeds[slice_])
        ax.add_collection(self.path_collection)

        cbar = fig.colorbar(self.path_collection, ax=ax, pad=0, aspect=60, format=EngFormatter(unit="m/s"))
        cbar.ax.tick_params(axis="y", labelsize=8)

        seg = self.data.paths[index]
        self.marker = ax.scatter(*seg.vertices[-1], c="white", marker="*", zorder=2)

        self.canvas = FigureCanvasTkAgg(fig, master=self)
        self.canvas.draw()
        self.canvas.mpl_connect("key_press_event", self.keypress)

        self._slice_size = tkinter.IntVar(value=slice_size)
        self._index = tkinter.IntVar(value=index)

        self._slice_size_spinbox = ttk.Spinbox(self, from_=0, to=len(self.data.paths) - 1, textvariable=self._slice_size, command=self.update_index, width=6)
        self._slice_size_spinbox.bind("<KeyRelease>", self.update_index)

        self._index_scale = tkinter.Scale(self, from_=0, to=len(self.data.paths) - 1, orient=tkinter.HORIZONTAL, variable=self._index, command=self.update_index)
        self._index_spinbox = ttk.Spinbox(self, from_=0, to=len(self.data.paths) - 1, textvariable=self._index, command=self.update_index, width=6)
        self._index_spinbox.bind("<KeyRelease>", self.update_index)

        self.info_value = tkinter.StringVar(value=",  ".join(self.get_info(index)))
        self.info_label = ttk.Label(self, textvariable=self.info_value)
        self.button_quit = ttk.Button(self, text="Quit", command=self.master.quit)
        self.toolbar_frame = ttk.Frame(master=self)
        NavigationToolbar2Tk(self.canvas, self.toolbar_frame).update()

    def get_info(self, index):
        info = [f"{k}={v[index]}" for k, v in self.data.syncpoints.items()]
        info.append(f"Restore={int(self.data.restores[index])}")
        info.append(f"BeamPower(W)={int(self.data.beampowers[index])}")
        info.append(f"SpotSize(μm)={int(self.data.spotsizes[index])}")
        info.append(f"Speed(m/s)={self.data.speeds[index]:.3f}")
        info.append(f"DwellTime(ms)={self.data.dwell_times[index]:.5f}")
        return info

    def update_index(self, _=None):
        index = self.cap(self._index.get())
        ss = self._slice_size.get() or 1
        slice_ = slice(self.cap(index + 1 - ss), self.cap(index) + 1)
        segs = self.data.paths[slice_]

        if segs:
            self.path_collection.set_paths(segs)
            self.path_collection.set_array(self.data.speeds[slice_])
            self.marker.set_offsets(segs[-1].vertices[-1])
            self.canvas.draw()

        self.info_value.set(",  ".join(self.get_info(index)))

    def keypress(self, event):
        key = event.key.lower()
        stepsize = {"": 1, "shift": 10, "ctrl": 100, "alt": 1000}.get(event.key.split("+")[0], 1)
        if key in {"right", "p"}:
            self._index.set(self.cap(self._index.get() + stepsize))
        elif key in {"left", "n"}:
            self._index.set(self.cap(self._index.get() - stepsize))
        elif key == "a":
            self._index.set(0)
        elif key == "e":
            self._index.set(len(self.data.paths) - 1)
        elif key in "0123456789":
            n = int(key)
            for i, k in enumerate(self.data.syncpoints):
                if i + 1 == n:
                    self.nextdifferent(self.data.syncpoints[k])
        elif key == "r":
            self.nextdifferent(self.data.restores)
        elif key == "b":
            self.nextdifferent(self.data.beampowers)
        elif key == "s":
            self.nextdifferent(self.data.spotsizes)
        self.update_index()

    def nextdifferent(self, array):
        start = self.cap(self._index.get())
        diff = array[start:] != array[start]
        if diff.any():
            self._index.set(start + np.argmax(diff))

    def setup_grid(self):
        self.canvas.get_tk_widget().grid(row=0, columnspan=4, sticky="NSWE")
        self._index_scale.grid(row=1, columnspan=4, sticky="NSWE")
        self.info_label.grid(row=2, column=0, sticky="SW")
        self._slice_size_spinbox.grid(row=2, column=1, sticky="SE")
        self._index_spinbox.grid(row=2, column=2, sticky="SE")
        self.button_quit.grid(row=2, column=3, sticky="SE")
        self.toolbar_frame.grid(row=3, columnspan=4, sticky="NSWE")

def main():
    parser = argparse.ArgumentParser(description="OBP data viewer")
    parser.add_argument("obp_file", type=pathlib.Path, help="Path to obp file.")
    parser.add_argument("--slice-size", type=int, default=9999, help="Initial slice size.")
    parser.add_argument("--index", type=int, default=100, help="Initial index.")
    args = parser.parse_args()

    obp_objects = load_obp_objects(args.obp_file)
    data = load_artist_data(obp_objects)

    root = tkinter.Tk()
    root.title(f"OBP Viewer - {args.obp_file.name}")
    frame = ObpFrame(root, data, args.slice_size, args.index)
    frame.grid(row=0, column=0, sticky="NSWE", padx=5, pady=5)
    frame.setup_grid()
    root.mainloop()

if __name__ == "__main__":
    main()
