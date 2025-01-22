from window_recorder.recorder import WindowRecorder
import time
import logging

ch = logging.StreamHandler()

logging.basicConfig(level=logging.DEBUG,
                    format='[%(levelname)s %(asctime)s %(pathname)s:%(lineno)d] %(message)s',
                    datefmt='%m-%d %H:%M:%S', handlers=[ch])

vid_path="Captures/uniq12345.mp4"

with WindowRecorder(["WhatsApp Web"],video_path=vid_path):
    start = time.time()
    i = 1
    while time.time() - start < 2:
        i += 1
        time.sleep(0.1)


import panel as pn
import bencher as bch
vid_path=bch.VideoWriter.convert_to_compatible_format(vid_path)
print(vid_path)
# exit()
pn.pane.Video(vid_path).show()