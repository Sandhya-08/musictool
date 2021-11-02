import io
import os
import queue
import random
import string
import subprocess
import sys
import time
from pathlib import Path
from threading import Event
from threading import Thread

import numpy as np
from PIL import Image
from PIL import ImageDraw
from PIL import ImageFont

from musictools import config
from musictools.daw.midi.parse import ParsedMidi
from musictools.daw.streams.base import Stream
from musictools.util import float32_to_int16

# https://support.google.com/youtube/answer/6375112


# TODO: change to thread-safe queue.Queue
#   also compare speed of appendleft, pop vs append, popleft?
# audio_data = collections.deque()
# qsize = 2 ** 9
# qsize = 2 ** 4
# qsize = 2 ** 6
qsize = 2 ** 8
q_audio = queue.Queue(maxsize=qsize)
q_video = queue.Queue(maxsize=qsize)
# video_data = collections.deque()
# no_more_data = False
audio_seconds_written = 0.
video_seconds_written = 0.
frames_written = 0  # video
samples_written = 0  # audio

n_runs = 0
# fig, ax = plt.subplots(figsize=(frame_width / 100, frame_height / 100), frameon=False, dpi=100)
# ax.grid(False)
# ax.axis('off')

# R = np.random.randint(-200, 0, size=(frame_height, frame_width))
# im = plt.imshow(R)

font = ImageFont.truetype('static/fonts/SFMono-Semibold.otf', 30)
font2 = ImageFont.truetype('static/fonts/SFMono-Regular.otf', 20)
layer = Image.new('RGBA', (config.frame_width, config.frame_height), (255, 255, 255, 0))
text_color = (0, 0, 0)
d = ImageDraw.Draw(layer)


class PipeWriter(Thread):
    def __init__(self, pipe, q: queue.Queue):
        super().__init__()
        self.pipe = pipe
        self.q = q
        self.stream_finished = Event()
        # self.log = open(f'logs/{self.pipe}_log.jsonl', 'w')

    def run(self):
        with open(self.pipe, 'wb') as pipe:
            while not self.stream_finished.is_set() or not self.q.empty():
                # print(self.pipe, self.q.empty(), self.stream_finished.is_set(), 'foo')
                # if self.pipe == config.video_pipe: print(self.pipe, self.q.qsize(), 'lol')
                # print(json.dumps({'timestamp': time.monotonic(), 'writer': self.pipe, 'event': 'write_start', 'qsize': self.q.qsize()}), file=self.log)

                # you can't block w/o timeout because stream_finished event may be set at any time
                try:
                    b = self.q.get(block=True, timeout=0.01)
                except queue.Empty:
                    pass
                else:
                    pipe.write(b)
                    self.q.task_done()
                # print(json.dumps({'timestamp': time.monotonic(), 'writer': self.pipe, 'event': 'write_stop', 'qsize': self.q.qsize()}), file=self.log)

    # def run(self):
    #     # fd = os.open(self.pipe, os.O_WRONLY | os.O_NONBLOCK)
    #     fd = os.open(self.pipe, os.O_WRONLY)
    #     while not self.stream_finished.is_set():
    #         print(self.pipe, 'lol')
    #         b = self.q.get(block=True)
    #         print(self.pipe, 'kek')
    #         os.write(fd, b)
    #         self.q.task_done()
    #     os.close(fd)


class Video(Stream):

    def render_chunked(self, track: ParsedMidi):
        super().render_chunked(track)
        self.clear_background()

    def clear_background(self):
        self.background_draw.rectangle((0, 0, config.frame_width, config.frame_height), fill=(200, 200, 200))

    def __enter__(self):
        # with open('static/images_backup.pkl', 'rb') as f: self.images = [i.getvalue() for i in pickle.load(f)]
        # with open('static/images.pkl', 'rb') as f: self.images = pickle.load(f)

        def recreate(p):
            p = Path(p)
            if p.exists():
                p.unlink()
            os.mkfifo(p)

        recreate(config.audio_pipe)
        recreate(config.video_pipe)

        # INPUT_AUDIO = config.audio_pipe

        # thread_queue_size = str(2**16)
        thread_queue_size = str(2**10)
        # thread_queue_size = str(2**5)
        # thread_queue_size = str(2 ** 8)
        keyframe_seconds = 3

        cmd = ('ffmpeg',
               # '-loglevel', 'trace',
               '-threads', '2',
               # '-y', '-r', '60', # overwrite, 60fps
               '-re',
               '-y',

               # '-err_detect', 'ignore_err',
               '-f', 's16le',  # means 16bit input
               '-acodec', 'pcm_s16le',  # means raw 16bit input
               '-r', str(config.sample_rate),  # the input will have 44100 Hz
               '-ac', '1',  # number of audio channels (mono1/stereo=2)
               # '-thread_queue_size', thread_queue_size,
               '-thread_queue_size', '1024',
               '-i', config.audio_pipe,


               '-s', f'{config.frame_width}x{config.frame_height}',  # size of image string
               '-f', 'rawvideo',
               '-pix_fmt', 'rgba',  # format
               # '-r', str(config.fps),
               '-r', str(config.fps),  # input framrate. This parameter is important to stream w/o memory overflow
               # '-vsync', 'cfr', # kinda optional but you can turn it on
               # '-f', 'image2pipe',
               # '-i', 'pipe:', '-', # tell ffmpeg to expect raw video from the pipe
               # '-i', '-',  # tell ffmpeg to expect raw video from the pipe
               '-thread_queue_size', thread_queue_size,
               # '-blocksize', '2048',
               '-i', config.video_pipe,  # tell ffmpeg to expect raw video from the pipe

               # '-c:a', 'libvorbis',
               # '-ac', '1',  # number of audio channels (mono1/stereo=2)
               # '-b:a', "320k",  # output bitrate (=quality). Here, 3000kb/second

               '-c:v', 'libx264',
               '-pix_fmt', 'yuv420p',
               '-preset', 'ultrafast',
               '-tune', 'zerolatency',
               # '-tune', 'animation',
               # '-g', '150',  #  GOP: group of pictures
               '-g', str(keyframe_seconds * config.fps),  # GOP: group of pictures
               '-x264opts', 'no-scenecut',
               # '-x264-params', f'keyint={keyframe_seconds * config.fps}:scenecut=0',
               '-vsync', 'cfr',
               # '-async', '1',
               # '-tag:v', 'hvc1', '-profile:v', 'main10',
               # '-b:v', '16M',
               # '-b:a', "300k",
               '-b:a', '128k',
               # '-b:v', '64k',
               '-b:v', '200k',
               # '-b:v', '12m',
               '-deinterlace',
               # '-r', str(config.fps),

               '-r', str(config.fps),  # output framerate
               # '-maxrate', '1000k',
               # '-map', '0:a',
               # '-map', '1:v',

               # '-b', '400k', '-minrate', '400k', '-maxrate', '400k', '-bufsize', '1835k',
               # '-b', '400k', '-minrate', '400k', '-maxrate', '400k', '-bufsize', '300m',

               # '-blocksize', '2048',
               # '-flush_packets', '1',
               '-f', 'flv',
               '-flvflags', 'no_duration_filesize',
               config.OUTPUT_VIDEO,
               )

        # self.ffmpeg = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        self.ffmpeg = subprocess.Popen(cmd)
        # self.p = None
        # time.sleep(5)
        # print(self.p)
        # print('2'* 100)

        # self.audio_thread = GenerateAudioToPipe()
        # self.video_thread = GenerateVideoToPipe()

        self.audio_thread = PipeWriter(config.audio_pipe, q_audio)
        self.video_thread = PipeWriter(config.video_pipe, q_video)
        self.audio_thread.start()
        self.video_thread.start()

        self.vbuff = io.BytesIO()

        # time.sleep(2)
        # print('sfsfsf')
        # self.audio_pipe = os.open(config.audio_pipe, os.O_WRONLY | os.O_NONBLOCK)
        # print('qq')
        # self.video_pipe = os.open(config.video_pipe, os.O_WRONLY | os.O_NONBLOCK)

        self.background = Image.new('RGBA', layer.size, (200, 200, 200))
        self.background_draw = ImageDraw.Draw(self.background)
        # self.log = open(config.log_path, 'w')
        self.t_start = time.time()
        return self

    def __exit__(self, type, value, traceback):
        self.audio_thread.stream_finished.set()
        self.video_thread.stream_finished.set()

        self.audio_thread.join()
        self.video_thread.join()
        self.ffmpeg.wait()

        os.unlink(config.audio_pipe)
        os.unlink(config.video_pipe)

        assert frames_written == int(audio_seconds_written * config.fps)
        print(frames_written, audio_seconds_written, int(audio_seconds_written * config.fps))
        # self.log.close()

    def write(self, data: np.ndarray):
        """
        TODO:
            track speed of audio generating here
            (timie.time, local fps)
            dont generate more if there's no need
        """

        global n_runs
        global audio_seconds_written
        global video_seconds_written
        global frames_written
        global samples_written

        seconds = len(data) / config.sample_rate
        b = float32_to_int16(data).tobytes()

        real_seconds = time.time() - self.t_start
        if real_seconds < audio_seconds_written:
            # print('sleeping for', audio_seconds_written - real_seconds)
            time.sleep(audio_seconds_written - real_seconds)

        # audio_written, video_written = False, False

        # write audio samples
        # self.path.write(float32_to_int16(data).tobytes())
        # a = float32_to_int16(data)#.tobytes()
        # ab = os.write(self.audio, a)

        # print('XG', len(b))
        # os.write(self.audio_pipe, b)
        # print('VVS')
        q_audio.put(b, block=True)
        samples_written += len(data)
        audio_seconds_written += seconds

        n_frames = int(audio_seconds_written * config.fps) - frames_written
        # assert n_frames > 0
        # if n_frames == 0:
        # if n_frames < 100:
        if n_frames < config.video_queue_item_size:
            # if n_frames < 1:
            # if n_frames < 300:
            return
        # n_frames = int(seconds * config.fps)# - frames_written
        # print('fffffffffff', n_frames)

        # self.vbuff.truncate(0)
        # assert self.vbuff.getvalue() == b''
        # progress_color = 0, 255, 0, 100

        start_px = int(config.frame_width * self.n / self.track.n_samples)  # like n is for audio (progress on track), px is for video (progress on frame)
        chunk_width = int(config.frame_width * len(data) / self.track.n_samples)

        chord_length = config.frame_width / len(self.track.meta['progression'])
        frame_dx = chunk_width // n_frames

        x = start_px

        for frame in range(n_frames):
            x += frame_dx
            d.rectangle((0, 0, config.frame_width, config.frame_height), fill=(200, 200, 200))
            # print(chord_length * chord_i, self.n * config.frame_width // self.track.n_samples - chord_length * chord_i)

            # self.vbuff.write(random.choice(self.images))
            # self.vbuff.write(layer.tobytes())
            # q_video.put(b, block=True)
            chord_i = int(x / chord_length)
            chord_start_px = int(chord_i * chord_length)

            chord = self.track.meta['progression'][chord_i]
            background_color = self.track.meta['scale'].note_colors[chord.root]
            scale = self.track.meta['scale'].note_scales[chord.root]

            self.background_draw.rectangle((chord_start_px, 0, x + frame_dx, config.frame_height), fill=background_color)

            out = Image.alpha_composite(layer, self.background)

            q = ImageDraw.Draw(out)
            q.text((120, 0), self.track.meta['bassline'], font=font, fill=text_color)
            q.text((0, 0), f"score{self.track.meta['rhythm_score']}", font=font2, fill=text_color)
            q.text((0, 60), self.track.meta['chords'], font=font2, fill=text_color)
            q.text((250, 60), f"dist{self.track.meta['dist']}", font=font2, fill=text_color)
            q.text((0, 160), f"root scale: {self.track.meta['scale'].root.name} {self.track.meta['scale'].name}", font=font2, fill=text_color)
            q.text((chord_start_px, 180), scale, font=font2, fill=text_color)
            q.text((0, 30), f"bass_decay{self.track.meta['bass_decay']}", font=font2, fill=text_color)
            q.text((0, 200), 'tandav.me', font=font, fill=text_color)
            q.text((200, 205), sys.platform, font=font2, fill=text_color)
            q.text((random.randrange(config.frame_width), random.randrange(config.frame_height)), random.choice(string.ascii_letters), font=font, fill=text_color)

            # q_video.put(random.choice(self.images), block=True)
            q_video.put(out.tobytes(), block=True)

        # q_video.put(b''.join(random.choices(self.images, k=n_frames)), block=True)
        # q_video.put(self.vbuff.getvalue(), block=True)
        frames_written += n_frames
        video_seconds_written += n_frames / config.fps

        print('eeeeeeeeeeeeeeeeee', f'QA{q_audio.qsize()} QV{q_video.qsize()} {seconds=} {n_frames=} {frames_written=} {samples_written=} {audio_seconds_written=:.2f}')
        # info = {
        #     'timestamp': time.monotonic(),
        #     'qa': q_audio.qsize(),
        #     'qv': q_video.qsize(),
        #     'seconds': seconds,
        #     'n_frames': n_frames,
        #     'frames_written': frames_written,
        #     'samples_written': samples_written,
        #     'audio_seconds_written': audio_seconds_written,
        #     'video_seconds_written': video_seconds_written,
        # }
        # print(json.dumps(info), file=self.log)
