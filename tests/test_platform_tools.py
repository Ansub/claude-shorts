"""Offline regression checks for native paths, downloads and subprocess arguments."""
import importlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import platform_tools as pt
import get_music


class NativeTests(unittest.TestCase):
    def test_windows_venv_and_private_exe_without_path_refresh(self):
        with tempfile.TemporaryDirectory(prefix='shorts space é ') as td:
            cache = Path(td)
            (cache / 'bin').mkdir()
            exe = cache / 'bin' / 'whisper-cli.exe'
            exe.touch(); exe.chmod(0o755)
            with patch.object(pt, 'CACHE', cache), patch.object(pt.os, 'name', 'nt'), patch.object(pt.shutil, 'which', return_value=None):
                self.assertEqual(pt.venv_python(), cache / 'venv' / 'Scripts' / 'python.exe')
                self.assertEqual(pt.find_tool('whisper-cli'), str(exe))

    def test_missing_tool_is_actionable(self):
        with tempfile.TemporaryDirectory() as td, patch.object(pt, 'CACHE', Path(td)), patch.object(pt.shutil, 'which', return_value=None):
            with self.assertRaisesRegex(FileNotFoundError, 'setup.ps1'):
                pt.find_tool('absent')

    def test_model_download_resumes_and_is_rerunnable(self):
        data = b'0123456789'
        calls = []
        class Resp:
            def __init__(self, body, status): self.body, self.status = body, status; self.headers = {'Content-Length': str(len(body))}
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self, n=-1):
                out, self.body = self.body, b''
                return out
        def urlopen(req, timeout=None):
            rng = req.get_header('Range')
            calls.append(rng)
            if not rng:  # first try drops halfway
                Path(str(target) + '.part').write_bytes(data[:4])
                raise OSError('connection reset')
            start = int(rng.split('=')[1].rstrip('-'))
            return Resp(data[start:], 206)
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / 'model.bin'
            with patch.object(pt.urllib.request, 'urlopen', side_effect=urlopen):
                pt.download_model(target); pt.download_model(target)
            self.assertEqual(target.read_bytes(), data)
            self.assertEqual(calls, [None, 'bytes=4-'])
            self.assertFalse(target.with_suffix('.bin.part').exists())

    def test_windows_svg_dispatch_never_imports_cairo(self):
        class Renderer:
            @staticmethod
            def svg_to_bytes(**kw):
                return kw
        with patch.object(pt.sys, 'platform', 'win32'), patch.dict(sys.modules, {'resvg_py': Renderer}):
            self.assertEqual(pt.svg_to_png('C:/Users/Name/logo.svg', 42), {'svg_path': 'C:/Users/Name/logo.svg', 'height': 42})

    def test_music_updates_private_python_and_keeps_arguments_intact(self):
        with tempfile.TemporaryDirectory(prefix='music space é ') as td:
            python = Path(td) / 'python.exe'; python.touch()
            url = 'https://example.com/watch?v=one&list=two'
            with patch.object(sys, 'argv', ['get_music.py', url, td]), patch.object(get_music, 'venv_python', return_value=python), patch.object(get_music, 'find_tool', return_value=str(Path(td) / 'ffmpeg.exe')), patch.object(get_music.subprocess, 'run') as run:
                get_music.main()
            self.assertEqual(run.call_args_list[0].args[0][:4], [str(python), '-m', 'pip', 'install'])
            self.assertEqual(run.call_args_list[1].args[0][-2:], ['--', url])
            self.assertIn(str(Path(td).resolve() / '%(title)s.%(ext)s'), run.call_args_list[1].args[0])

    def test_whisper_failure_does_not_become_empty_transcript(self):
        import transcribe
        with patch.object(transcribe, 'find_tool', return_value='whisper-cli.exe'), patch.object(transcribe.subprocess, 'run', side_effect=subprocess.CalledProcessError(1, 'whisper')):
            with self.assertRaises(subprocess.CalledProcessError):
                transcribe.transcribe('model.bin', 'clip.wav', 0)


if __name__ == '__main__':
    unittest.main()
