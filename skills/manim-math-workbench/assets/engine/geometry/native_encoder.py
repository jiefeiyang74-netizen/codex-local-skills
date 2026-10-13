"""Explicit NVENC fixed profile; scene-local writer, no global patch or fallback."""
import subprocess, hashlib, json
from pathlib import Path
import numpy as np
from manim import config
PROFILE={'codec':'h264_nvenc','preset':'p5','rc':'vbr','cq':'22','bitrate':'0','pix_fmt':'yuv420p','input_format':'rgba','schema':'encoder-profile-v1','video_track_timescale':60000,'movie_timescale':60000}

def ensure_exact_partial(path, frames, ffmpeg_exe):
 """Validate N/60, repair only container timing if needed; never re-encode."""
 import av
 from fractions import Fraction
 path=Path(path)
 expected=Fraction(frames,60)
 def check(p):
  with av.open(str(p)) as c:
   s=c.streams.video[0]
   packets=[q for q in c.demux(s) if q.dts is not None]
   pts=sorted(q.pts*q.time_base for q in packets)
   durations=sum((q.duration*q.time_base for q in packets),Fraction(0))
   return s.frames==frames and s.average_rate==60 and s.duration*s.time_base==expected and len(pts)==frames and all(t==Fraction(i,60) for i,t in enumerate(pts)) and durations==expected
 if check(path):return {'remuxed':False,'frames':frames,'duration':str(expected)}
 target=path.with_name(path.stem+'.clockfix.mp4')
 cmd=[str(ffmpeg_exe),'-hide_banner','-loglevel','error','-nostdin','-y','-i',str(path),'-map','0:v:0','-c:v','copy','-video_track_timescale','60000','-movie_timescale','60000',str(target)]
 completed=subprocess.run(cmd,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=45,creationflags=subprocess.BELOW_NORMAL_PRIORITY_CLASS|subprocess.CREATE_NO_WINDOW)
 if completed.returncode or not check(target):raise RuntimeError('Partial packet clock repair failed; keep artifact for diagnosis')
 target.replace(path)
 return {'remuxed':True,'frames':frames,'duration':str(expected)}

def native_writer(ffmpeg_exe, expected_sha256):
 from manim.scene.scene_file_writer import SceneFileWriter
 executable=Path(ffmpeg_exe)
 if not executable.is_absolute() or not executable.is_file():raise ValueError('Trusted absolute FFmpeg executable required')
 if hashlib.sha256(executable.read_bytes()).hexdigest()!=expected_sha256:raise ValueError('FFmpeg executable identity changed')
 if config.frame_rate!=60:raise ValueError('Fixed profile requires exactly60fps')
 if config.transparent or config.movie_file_extension!='.mp4':raise ValueError('Fixed profile supports opaque MP4 only')
 def open_partial_movie_stream(self,file_path=None):
  if file_path is None:file_path=self.partial_movie_files[self.renderer.num_plays]
  self.partial_movie_file_path=file_path
  logpath=Path(str(file_path)+'.nvenc.log');self._nvenc_log=logpath.open('wb')
  cmd=[str(executable),'-hide_banner','-loglevel','error','-nostdin','-y','-threads','4','-filter_threads','2','-f','rawvideo','-pixel_format','rgba','-video_size',f'{config.pixel_width}x{config.pixel_height}','-framerate',str(config.frame_rate),'-i','pipe:0','-an','-c:v','h264_nvenc','-preset','p5','-rc','vbr','-cq','22','-b:v','0','-pix_fmt','yuv420p','-video_track_timescale','60000','-movie_timescale','60000',str(file_path)]
  try:self._nvenc_process=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=self._nvenc_log,creationflags=subprocess.BELOW_NORMAL_PRIORITY_CLASS|subprocess.CREATE_NO_WINDOW)
  except BaseException:self._nvenc_log.close();raise
  self._nvenc_frames=0
 def write_frame(self,frame_or_renderer,num_frames=1):
  frame=frame_or_renderer
  if not isinstance(frame,np.ndarray) or frame.dtype!=np.uint8 or frame.shape!=(config.pixel_height,config.pixel_width,4):raise ValueError('Expected native Cairo uint8 RGBA at configured dimensions')
  if not isinstance(num_frames,int) or num_frames<1:raise ValueError('Invalid native repeat count')
  data=frame.tobytes(order='C') # One copy per original native call; frozen waits reuse identical bytes only.
  for _ in range(num_frames):
   written=self._nvenc_process.stdin.write(data)
   if written!=len(data):raise IOError('Short RGBA write')
  self._nvenc_frames+=num_frames
 def close_partial_movie_stream(self):
  p=self._nvenc_process
  try:
   try:p.stdin.close()
   except BrokenPipeError:pass
   try:code=p.wait(timeout=45)
   except subprocess.TimeoutExpired:
    p.kill();p.wait();raise RuntimeError('Owned NVENC encoder close timeout')
   if code!=0:raise RuntimeError(f'NVENC failed with exit {code}; see {self.partial_movie_file_path}.nvenc.log')
  finally:self._nvenc_log.close()
  self._nvenc_clock_receipt=ensure_exact_partial(self.partial_movie_file_path,self._nvenc_frames,executable)
 class NativeGeometrySceneFileWriter(SceneFileWriter):
  pass
 NativeGeometrySceneFileWriter.open_partial_movie_stream=open_partial_movie_stream
 NativeGeometrySceneFileWriter.write_frame=write_frame
 NativeGeometrySceneFileWriter.close_partial_movie_stream=close_partial_movie_stream
 return NativeGeometrySceneFileWriter


PROFILE_NAME = 'nvenc_p5_cq22_rgba_60_v1'

def encoder_contract(profile, ffmpeg_exe):
 """Path stays in local runtime; portable identity includes binary and fixed args."""
 if profile in (None, 'software'):
  return {'profile': 'software'}
 if profile != PROFILE_NAME:
  raise ValueError('Unknown explicit final_encoder_profile')
 executable=Path(ffmpeg_exe)
 if not executable.is_absolute() or not executable.is_file():
  raise ValueError('Trusted absolute FFmpeg executable required')
 return {'profile': PROFILE_NAME, **PROFILE,
         'ffmpeg_sha256': hashlib.sha256(executable.read_bytes()).hexdigest(),
         'writer_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
         'arguments': ['-threads','4','-filter_threads','2','-f','rawvideo',
          '-pixel_format','rgba','-framerate','60','-an','-c:v','h264_nvenc',
          '-preset','p5','-rc','vbr','-cq','22','-b:v','0','-pix_fmt','yuv420p',
          '-video_track_timescale','60000','-movie_timescale','60000'],
         'partial_clock': 'exact_N_over_60_lossless_remux_60000_v1'}

def encoder_cache_identity(content_identity, contract):
 if contract == {'profile': 'software'}:
  return content_identity
 return hashlib.sha256((content_identity + json.dumps(contract,sort_keys=True)).encode()).hexdigest()
