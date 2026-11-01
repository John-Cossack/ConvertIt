"""AVIF RGB lossless encoding, avoiding a lossy RGB → YUV round trip."""
from pathlib import Path
import tempfile

from audio import binary, run


def save_avif(frames, destination, durations, loop=0):
    with tempfile.TemporaryDirectory(prefix=".convert-avif-", dir=Path(destination).parent) as folder:
        source = Path(folder) / "frames.png"
        settings = {}
        if len(frames) > 1:
            settings.update(save_all=True, append_images=frames[1:], duration=durations, loop=0, disposal=0, blend=0)
        frames[0].save(source, format="PNG", **settings)
        alpha = any(frame.mode == "RGBA" and frame.getextrema()[3][0] != 255 for frame in frames)
        if alpha:
            mapping = ["-filter_complex", "[0:v]split[r][a];[r]format=gbrp[c];[a]alphaextract,setparams=colorspace=bt709[alpha]",
                       "-map", "[c]", "-map", "[alpha]"]
        else:
            mapping = ["-vf", "format=gbrp", "-map", "0:v:0"]
        run([binary("ffmpeg"), "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
             "-i", str(source), *mapping, "-c:v", "libaom-av1", "-crf", "0", "-b:v", "0",
             "-cpu-used", "4", "-threads", "4", "-still-picture", "1" if len(frames) == 1 else "0",
             "-fps_mode", "passthrough", "-loop", str(loop), "-f", "avif", str(destination)])
