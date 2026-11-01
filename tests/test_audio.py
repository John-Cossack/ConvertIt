import json
import math
from pathlib import Path
import struct
import tempfile
import unittest
import wave

from audio import AUDIO_FORMATS, binary, probe, run
from converter import convert
from capabilities import available, selection_groups


class AudioTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parent.parent / "test-results"
        root.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="audio-", dir=root)
        self.folder = Path(self.temp.name)
        self.source = self.folder / "Звук & тест.wav"
        samples = b"".join(struct.pack("<hh", int(20000 * math.sin(i * 0.13)), int(14000 * math.cos(i * 0.17))) for i in range(22050))
        with wave.open(str(self.source), "wb") as out:
            out.setnchannels(2)
            out.setsampwidth(2)
            out.setframerate(44100)
            out.writeframes(samples)
        self.original = self.source.read_bytes()

    def tearDown(self):
        self.temp.cleanup()

    def decoded(self, path, fmt="s32le", codec="pcm_s32le"):
        return run([binary("ffmpeg"), "-v", "error", "-i", str(path), "-map", "0:a:0", "-c:a", codec, "-f", fmt, "pipe:1"])

    def test_every_audio_output(self):
        expected = {"wav":"pcm_s16le", "flac":"flac", "m4a":"alac", "m4b":"alac", "aiff":"pcm_s16be",
                    "mp3":"mp3", "aac":"aac", "ogg":"vorbis", "opus":"opus", "ac3":"ac3", "wma":"wmav2",
                    "au":"pcm_s16be", "caf":"pcm_s16le", "weba":"opus", "aif":"pcm_s16be", "aifc":"pcm_f64be", "oga":"vorbis", "amr":"amr_wb", "voc":"pcm_s16le"}
        for target in AUDIO_FORMATS:
            with self.subTest(target=target):
                source = self.source
                if target == "wav":
                    source = convert(self.source, "flac")
                    source = source.rename(self.folder / "інший вхід.flac")
                output = convert(source, target)
                info = probe(output)
                self.assertEqual(info["codec_name"], expected[target])
                self.assertEqual(info["channels"], 1 if target=='amr' else 2)
                self.assertEqual(int(info["sample_rate"]), 16000 if target=='amr' else 48000 if target in {"opus", "weba"} else 44100)
                self.assertEqual(output.stem, source.stem)
                self.assertEqual(output.parent, source.parent)
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_lossless_pcm_equality(self):
        original = self.decoded(self.source)
        for target in ("flac", "m4a", "m4b", "aiff", "au", "caf"):
            with self.subTest(target=target):
                self.assertEqual(self.decoded(convert(self.source, target)), original)

    def test_24_and_32_bit_audio(self):
        for bits in (24, 32):
            source = self.folder / f"precision-{bits}.wav"
            run([binary("ffmpeg"), "-v", "error", "-i", str(self.source), "-af", "volume=0.999123", "-c:a", f"pcm_s{bits}le", str(source)])
            expected = self.decoded(source)
            for target in (("flac", "m4a", "aiff", "caf") if bits == 24 else ("flac", "aiff", "caf")):
                with self.subTest(bits=bits, target=target):
                    self.assertEqual(self.decoded(convert(source, target)), expected)
            if bits == 32:
                with self.assertRaisesRegex(ValueError, "24"):
                    convert(source, "m4a")

    def test_float_precision(self):
        source = self.folder / "float.wav"
        run([binary("ffmpeg"), "-v", "error", "-i", str(self.source), "-c:a", "pcm_f64le", str(source)])
        output = convert(source, "caf")
        self.assertEqual(self.decoded(source, "f64le", "pcm_f64le"), self.decoded(output, "f64le", "pcm_f64le"))
        with self.assertRaisesRegex(ValueError, "float"):
            convert(source, "flac")

    def test_existing_output_and_original_protected(self):
        output = self.source.with_suffix(".mp3")
        output.write_bytes(b"existing")
        with self.assertRaises(FileExistsError):
            convert(self.source, "mp3")
        self.assertEqual(output.read_bytes(), b"existing")
        with self.assertRaises(ValueError):
            convert(self.source, "wav", overwrite=True)
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_corrupt_and_no_audio(self):
        corrupt = self.folder / "bad.mp3"
        corrupt.write_bytes(b"not audio")
        with self.assertRaises(ValueError):
            convert(corrupt, "flac")
        self.assertEqual(list(self.folder.glob(".convert-*")), [])

    def test_high_rate_never_silently_reduced_for_mp3(self):
        source = self.folder / "96khz.wav"
        run([binary("ffmpeg"), "-v", "error", "-i", str(self.source), "-ar", "96000", str(source)])
        with self.assertRaisesRegex(ValueError, "96000"):
            convert(source, "mp3")
        result = convert(source, "flac")
        self.assertEqual(int(probe(result)["sample_rate"]), 96000)
        self.assertEqual(self.decoded(source), self.decoded(result))

    def test_remux_avoids_lossy_generation(self):
        source = convert(self.source, "mp3")
        renamed = source.rename(source.with_suffix(".mp2"))
        expected = self.decoded(renamed)
        output = convert(renamed, "mp3")
        self.assertEqual(self.decoded(output), expected)

    def test_metadata(self):
        source = self.folder / "tagged.wav"
        run([binary("ffmpeg"), "-v", "error", "-i", str(self.source), "-c:a", "copy", "-metadata", "title=Український тест", str(source)])
        result = convert(source, "flac")
        info = json.loads(run([binary("ffprobe"), "-v", "error", "-show_format", "-of", "json", str(result)]))
        tags = {key.lower(): value for key, value in info["format"]["tags"].items()}
        self.assertEqual(tags["title"], "Український тест")

    def mp3_source(self):
        return convert(self.source, "mp3").rename(self.folder / "Вхід MP3.mp3")

    def test_mp3_routes_match_screenshot(self):
        expected = ["aac", "aiff", "flac", "m4a", "mp3", "wav", "wma"]
        self.assertEqual([row["id"] for row in available("MP3", "audio")], expected)
        groups = selection_groups([self.folder / "TRACK.MP3"])
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0][0], "Аудіо")
        self.assertEqual([row["id"] for row in groups[0][1]], expected)
        mixed = selection_groups([self.source, self.folder / "track.mp3"])
        self.assertEqual([row["id"] for row in mixed[0][1]], expected)
        self.assertEqual(len(available("audio", "audio")), 19)

    def test_mp3_all_allowed_conversions_and_precision(self):
        source = self.mp3_source()
        original = source.read_bytes()
        expected = {"aac":"aac", "aiff":"pcm_s24be", "flac":"flac", "m4a":"alac", "wav":"pcm_f32le", "wma":"wmav2"}
        reference24 = self.decoded(source, "s24le", "pcm_s24le")
        reference_float = self.decoded(source, "f32le", "pcm_f32le")
        for target, codec in expected.items():
            with self.subTest(target=target):
                output = convert(source, target)
                info = probe(output)
                self.assertEqual(info["codec_name"], codec)
                self.assertEqual(int(info["sample_rate"]), 44100)
                self.assertEqual(info["channels"], 2)
                self.assertEqual(output.stem, source.stem)
                if target in {"aiff", "flac", "m4a"}:
                    self.assertEqual(self.decoded(output, "s24le", "pcm_s24le"), reference24)
                if target == "wav":
                    self.assertEqual(self.decoded(output, "f32le", "pcm_f32le"), reference_float)
        with self.assertRaises(ValueError):
            convert(source, "mp3", overwrite=True)
        self.assertEqual(source.read_bytes(), original)

    def test_mp3_disallowed_routes_rejected_by_decoder(self):
        source = self.mp3_source()
        renamed = source.rename(source.with_suffix(".mp2"))
        for target in ("ogg", "opus", "ac3", "au", "caf", "weba", "m4b"):
            with self.subTest(target=target), self.assertRaisesRegex(ValueError, "MP3"):
                convert(renamed, target)
            self.assertFalse(renamed.with_suffix('.' + target).exists())


if __name__ == "__main__":
    unittest.main()
