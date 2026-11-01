"""Prepared audio must remain small, traceable and playable without FFmpeg at runtime."""
import array
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('audio_import', ROOT/'import-audio.py')
IMPORT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(IMPORT)
CATALOG = json.loads((ROOT/'public/audio-catalog.json').read_text(encoding='utf-8'))
FFMPEG = os.environ.get('ZZ_FFMPEG') or shutil.which('ffmpeg')


class AudioManifestTests(unittest.TestCase):
    def test_files_match_derived_hashes_and_provenance(self):
        self.assertEqual(CATALOG['version'], 2)
        self.assertEqual(len(CATALOG['clips']), 20)
        self.assertEqual({clip['id'] for clip in CATALOG['clips']}, {row[0] for row in IMPORT.SELECTION})
        self.assertEqual(sum(clip['bytes'] for clip in CATALOG['clips']), CATALOG['totalBytes'])
        self.assertLess(CATALOG['totalBytes'], CATALOG['sourceTotalBytes']*.6)
        self.assertNotRegex(json.dumps(CATALOG), r'[A-Z]:[/\\]|/Users/|/home/')
        for clip in CATALOG['clips']:
            with self.subTest(clip=clip['id']):
                data = (ROOT/'public'/clip['url']).read_bytes()
                self.assertEqual(len(data), clip['bytes'])
                self.assertEqual(hashlib.sha256(data).hexdigest(), clip['derivedSha256'])
                self.assertEqual(clip['sha256'], clip['derivedSha256'])
                self.assertRegex(clip['sourceSha256'], r'^[a-f0-9]{64}$')
                self.assertNotEqual(clip['sourceSha256'], clip['derivedSha256'])
                self.assertTrue(clip['source'].startswith('DragonSound/sounds/'))
                self.assertEqual(clip['offset'], 0)
                self.assertTrue(clip['prepared'])
                self.assertGreater(clip['duration'], 0)
                self.assertGreater(clip['processing']['fadeOut'], 0)

    def test_effects_are_ready_takes_and_ambience_keeps_its_timeline(self):
        for clip in CATALOG['clips']:
            with self.subTest(clip=clip['id']):
                if clip['kind'] == 'effect':
                    self.assertAlmostEqual(clip['duration'], clip['limit'], places=3)
                    self.assertLess(clip['bytes'], 30_000)
                    self.assertEqual(clip['processing']['channels'], 1)
                else:
                    self.assertIsNone(clip['limit'])
                    self.assertAlmostEqual(clip['duration'], clip['sourceDuration'], places=3)
        footsteps = next(clip for clip in CATALOG['clips'] if clip['id'] == 'footstep')
        self.assertGreater(footsteps['sourceDuration'], 160)
        self.assertEqual(footsteps['duration'], 1.1)
        self.assertLess(footsteps['bytes'], footsteps['sourceBytes']/100)

    def test_static_normalization_is_bounded_and_peak_aware(self):
        self.assertEqual(IMPORT.normalization(-60, -40, 'effect'), 9)
        self.assertEqual(IMPORT.normalization(-5, -.1, 'effect'), -13)
        self.assertEqual(IMPORT.normalization(-30, -1, 'effect'), -1)
        for clip in CATALOG['clips']:
            levels = clip['processing']
            self.assertGreaterEqual(levels['gainDb'], -18)
            self.assertLessEqual(levels['gainDb'], 9)
            self.assertLessEqual(levels['measuredPeakDb'] + levels['gainDb'], -1.99)


@unittest.skipUnless(FFMPEG, 'Set ZZ_FFMPEG to run actual codec/import integration tests')
class AudioCodecTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ffmpeg, cls.ffprobe = IMPORT.find_tools(FFMPEG)

    def decode(self, filename, channels=1):
        raw = subprocess.run([str(self.ffmpeg), '-nostdin', '-hide_banner', '-loglevel', 'error',
                              '-i', str(filename), '-f', 'f32le', '-ac', str(channels), '-ar', '32000', '-'],
                             check=True, capture_output=True, timeout=60).stdout
        samples = array.array('f')
        samples.frombytes(raw)
        return samples

    def test_every_shipped_clip_decodes_with_declared_duration_and_no_clipping(self):
        for clip in CATALOG['clips']:
            with self.subTest(clip=clip['id']):
                channels = clip['processing']['channels']
                samples = self.decode(ROOT/'public'/clip['url'], channels)
                self.assertAlmostEqual(len(samples)/32000/channels, clip['duration'], delta=.15)
                self.assertGreater(max(abs(value) for value in samples), .0001)
                self.assertLess(max(abs(value) for value in samples), 1)

    def test_repeat_import_is_deterministic_leaves_source_intact_and_fades_edges(self):
        with tempfile.TemporaryDirectory() as temporary:
            temporary = Path(temporary)
            sounds = temporary/'original/sounds'
            sounds.mkdir(parents=True)
            source = sounds/'tone.mp3'
            IMPORT.run([self.ffmpeg, '-nostdin', '-hide_banner', '-loglevel', 'error', '-f', 'lavfi',
                        '-i', 'sine=frequency=900:duration=4:sample_rate=32000', '-c:a', 'libmp3lame', '-b:a', '96k', source])
            before = source.read_bytes()
            selection = [('test', 'Тест', 'effect', 'tone.mp3', .5, 1.1, .4),
                         ('background', 'Фон', 'ambience', 'tone.mp3', 0, None, .4)]
            first = IMPORT.build_library(temporary/'original', temporary/'one', self.ffmpeg, selection)
            second = IMPORT.build_library(temporary/'original', temporary/'two', self.ffmpeg, selection)
            self.assertEqual(first, second)
            self.assertEqual(source.read_bytes(), before)
            take = first['clips'][0]
            self.assertEqual(take['sourceSha256'], hashlib.sha256(before).hexdigest())
            self.assertLess(take['bytes'], take['sourceBytes']/3)
            samples = self.decode(temporary/'one/audio/test.mp3')
            self.assertAlmostEqual(len(samples)/32000, 1.1, delta=.01)
            rms = lambda values: math.sqrt(sum(value*value for value in values)/len(values))
            center = rms(samples[8000:12000])
            self.assertLess(rms(samples[:160]), center*.5)
            self.assertLess(rms(samples[-640:]), center*.4)
            with self.assertRaisesRegex(ValueError, 'outside the source'):
                IMPORT.build_library(temporary/'original', sounds/'bad-output', self.ffmpeg, selection)


if __name__ == '__main__':
    unittest.main()
