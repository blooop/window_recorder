import os
import cv2
import time
import numpy as np
import subprocess
import logging
from multiprocessing import SimpleQueue, Process
from datetime import datetime
from mss.linux import MSS as mss
from window_recorder import cfg
from typing import Iterable, AnyStr
import signal

logger = logging.getLogger(__name__)
from ewmh import EWMH
def _record_loop(q: SimpleQueue, filename, monitor, frame_rate):
    with mss() as sct:
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        # adjust monitor to crop out the parts not visible
        if monitor['left'] < 0:
            monitor['width'] += monitor['left']
            monitor['left'] = 0
        if monitor['top'] < 0:
            monitor['height'] += monitor['top']
            monitor['top'] = 0
        monitor['height'] = min(monitor['height'], sct.monitors[0]['height'] - monitor['top'])
        monitor['width'] = min(monitor['width'], sct.monitors[0]['width'] - monitor['left'])
        out = cv2.VideoWriter(filename, fourcc, frame_rate, (monitor['width'], monitor['height']))
        period = 1. / frame_rate
        while q.empty():
            start_time = time.time()

            img = np.array(sct.grab(monitor))
            out.write(img[:, :, :3])

            # wait for frame rate time
            elapsed = time.time() - start_time
            if elapsed < period:
                time.sleep(period - elapsed)
        out.release()


class WindowRecorder:
    """Programatically video record a window in Linux (requires xwininfo)"""

    def __init__(self, window_names: Iterable[AnyStr] = None, frame_rate=30.0, name_suffix="", save_dir=None,video_path=None,
                 record=True,offset_x:float=0,offset_y:float=0,width_override:float=-1,height_override:float=-1):
        self.record = record
        if not self.record:
            return
        if window_names is None:
            logger.info("Select a window to record by left clicking with your mouse")
            output = subprocess.check_output(["xwininfo"], universal_newlines=True)
            logger.info(f"Selected {output}")
        else:
            window_manager_manager = EWMH()
            client_list = window_manager_manager.getClientList()

            active_window_names = []
            for window in client_list:
                active_window_names.append(window_manager_manager.getWmName(window).decode("utf-8"))
            # print(active_window_names)
            for name_pattern in window_names:
                name = name_pattern
                for window in active_window_names:
                    if name_pattern in window:
                        name=window
                try:
                    output = subprocess.check_output(["xwininfo", "-name", name], universal_newlines=True)
                    break
                except subprocess.CalledProcessError as e:
                    logger.debug(f"Could not find window named {name}, trying next in list")
                    pass
            else:
                raise RuntimeError(f"Could not find any windows with names from {window_names}")

        properties = {}
        for line in output.split("\n"):
            if ":" in line:
                parts = line.split(":", 1)
                properties[parts[0].strip()] = parts[1].strip()

        left, top = int(properties["Absolute upper-left X"]), int(properties["Absolute upper-left Y"])
        width, height = int(properties["Width"]), int(properties["Height"])
        left+= offset_x
        top+= offset_y
        if width_override>0:
            width = width_override
        if height_override>0:
            height = height_override


        self.monitor = {"top": top, "left": left, "width": width, "height": height}
        self.frame_rate = frame_rate
        self.suffix = name_suffix
        self.save_dir = save_dir
        if self.save_dir is None:
            self.save_dir = cfg.CAPTURE_DIR

        self.video_path=video_path

        # Register signal handlers
        self.record_process = None
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)

    def __enter__(self):
        if not self.record:
            return self
        os.makedirs(self.save_dir, exist_ok=True)
        if self.video_path is None:
            self.video_path = os.path.join(self.save_dir,
                                f"{datetime.now().strftime('%Y_%m_%d_%H_%M_%S')}_{self.suffix}.mp4")
        logger.debug(f"Recording video to {self.video_path}")
        self.q = SimpleQueue()
        self.record_process = Process(target=_record_loop,
                                      args=(self.q, self.video_path, self.monitor, self.frame_rate))
        self.record_process.start()
        return self

    def __exit__(self, *args):
        if not self.record:
            return
        self.cleanup()

    def cleanup(self):
        """Cleanup resources."""
        if self.record_process and self.record_process.is_alive():
            self.q.put('die')
            self.record_process.join()
            cv2.destroyAllWindows()

    def signal_handler(self, signum, frame):
        """Signal handler to ensure context manager cleanup runs on SIGINT/SIGTERM."""
        print(f"Received signal: {signal.Signals(signum).name}")
        self.cleanup()
        # Optionally re-raise the signal to Python to allow the interrupt to propagate further
        os.kill(os.getpid(), signum)
