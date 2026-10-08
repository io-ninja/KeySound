"""Regression checks; no global input hooks or hardware playback by default."""
import sys
import unittest
from pathlib import Path
import keysound as app


class BackendTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform == 'darwin', 'macOS native decoder')
    def test_mac_decoder_preserves_native_buffer(self):
        buffer = app.decode_audio(app.BASE / 'packs/gunshot/gunshot.wav')
        self.assertGreater(buffer.frameLength(), 0)
        self.assertEqual(buffer.format().channelCount(), 1)


    def test_windows_scan_codes_and_repeat(self):
        from windows_backend import key_event
        held = set()
        self.assertEqual(key_event(0x100, 0x1e, 0, held), 0)  # Physical A, not VK_A=65.
        self.assertIsNone(key_event(0x100, 0x1e, 0, held))
        self.assertIsNone(key_event(0x101, 0x1e, 0, held))
        self.assertEqual(key_event(0x100, 0x1c, 0, held), 36)
        self.assertEqual(key_event(0x100, 0x1c, 1, held), 76)
        self.assertEqual(key_event(0x104, 0x38, 1, held), 61)
        self.assertIsNone(key_event(0x105, 0x38, 1, held))
        self.assertEqual(key_event(0x100, 0x39, 0, held), 49)
        self.assertEqual(key_event(0x100, 0x4b, 1, held), 123)
        self.assertEqual(key_event(0x100, 0xff, 0, held), -1)


    def test_windows_audio_mixes_buffers_and_limits_voices(self):
        import numpy as np
        from unittest.mock import patch
        from windows_backend import Audio
        pack = app.read_pack(app.BASE / 'packs/gunshot')
        with patch('windows_backend.Audio._open_stream'):
            audio = Audio(pack, 2, 0.5)
        try:
            audio.buffers = {'test': np.ones((4, 2), dtype='float32')}
            with patch.object(audio, 'is_running', return_value=True):
                self.assertTrue(audio.play('test'))
                self.assertTrue(audio.play('test'))
                self.assertFalse(audio.play('test'))
            output = np.zeros((8, 2), dtype='float32')
            audio._render(output, 8, None, None)
            np.testing.assert_allclose(output[:4], 0.5)
            np.testing.assert_array_equal(output[4:], 0)
            self.assertFalse(any(audio.voices))
            audio.stop()
            audio._render(output, 8, None, None)
            self.assertFalse(output.any())
        finally:
            audio.close()


    def test_windows_decoder_limits_and_conversion(self):
        import tempfile
        import numpy as np
        import soundfile as sf
        from windows_backend import decode_audio, convert_audio
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'audio.wav'
            sf.write(path, np.ones((480, 1), dtype='float32') * 0.25, 48000)
            data, rate = decode_audio(path)
            converted = convert_audio(data, rate, 44100, 2)
            self.assertEqual(converted.shape, (441, 2))
            np.testing.assert_allclose(converted, 0.25, atol=0.0001)
            sf.write(path, np.zeros((80001, 1), dtype='float32'), 8000)
            with self.assertRaises(ValueError):
                decode_audio(path)
            path.write_bytes(b'RIFF' + b'\0' * 4 + b'WAVE' + b'\0' * 32)
            with self.assertRaises(ValueError):
                decode_audio(path)
            mp3 = Path(folder) / 'audio.mp3'
            sf.write(mp3, np.sin(np.arange(4800) * 0.1).astype('float32'), 48000, format='MP3')
            decoded, rate = decode_audio(mp3)
            self.assertGreater(np.max(np.abs(decoded)), 0)
            self.assertEqual(rate, 48000)

    def test_shared_api_with_fake_audio_device(self):
        import json
        import tempfile
        import threading
        import urllib.request
        import numpy as np
        from unittest.mock import patch
        from windows_backend import Audio, decode_audio

        class FakeStream:
            active = False
            def __init__(self, **kwargs):
                self.callback = kwargs['callback']
            def start(self):
                self.active = True
            def close(self):
                self.active = False

        with tempfile.TemporaryDirectory() as folder, patch.object(app, 'Audio', Audio), patch.object(app, 'decode_audio', decode_audio), patch('sounddevice.query_devices', return_value={'default_samplerate':48000, 'max_output_channels':2}), patch('sounddevice.OutputStream', FakeStream):
            instance = app.App(Path(folder))
            server = app.make_server(instance, 0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            origin = 'http://127.0.0.1:' + str(server.server_port)
            def request(route, body=None, headers=None):
                fields = {'X-Keysound':'1', 'Origin':origin, 'Content-Type':'application/json'}
                fields.update(headers or {})
                raw = body if isinstance(body, bytes) else (json.dumps(body).encode() if body is not None else None)
                with urllib.request.urlopen(urllib.request.Request(origin + route, data=raw, headers=fields), timeout=5) as response:
                    return json.load(response)
            try:
                self.assertTrue(request('/api/state')['status']['audio'])
                request('/api/config', {'volume':0.5, 'mode':'per-key'})
                self.assertEqual(app.load_config(Path(folder)/'config.json')['volume'], 0.5)
                request('/api/mapping', {'key':'36','sound':'gunshot.wav'})
                self.assertTrue(request('/api/preview', {'sound':'gunshot.wav'})['played'])
                output = np.zeros((20000, 2), dtype='float32')
                instance.audio._render(output, len(output), None, None)
                self.assertGreater(np.max(np.abs(output)), 0)
                state = request('/api/upload', (app.BASE/'packs/gunshot/gunshot.wav').read_bytes(), {'X-Filename':'test.wav'})
                self.assertEqual(len(next(p for p in state['packs'] if p['id']=='custom')['files']), 1)
                request('/api/config', {'pack':'custom'})
                self.assertEqual(instance.config['pack'], 'custom')
                instance.audio.stream.close()
                name = instance.packs['custom']['files'][0]
                self.assertTrue(request('/api/preview', {'sound':name})['played'])
                self.assertTrue(instance.audio.is_running())
                self.assertEqual(instance.audio.volume, 0.5)
                instance.audio.stop()
                request('/api/config', {'enabled':True, 'debounce_ms':0})
                self.assertTrue(instance.trigger(36))
                import time
                deadline = time.monotonic() + 2
                while not any(instance.audio.voices) and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertTrue(instance.worker.is_alive())
                instance.audio._render(output, len(output), None, None)
                self.assertGreater(np.max(np.abs(output)), 0)
                request('/api/config', {'enabled':False})
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)
                instance.close()

    @unittest.skipUnless(sys.platform == 'win32', 'real Windows hook startup/shutdown')
    def test_windows_hook_start_stop(self):
        import threading
        import time
        from types import SimpleNamespace
        from windows_backend import listen
        instance = SimpleNamespace(config={'enabled':False}, quit=threading.Event(),
                                   lock=threading.RLock(), listener_ready=False, listener_error='')
        thread = threading.Thread(target=listen, args=(instance,), daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 5
            while thread.is_alive() and not instance.listener_ready and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertTrue(instance.listener_ready, instance.listener_error)
        finally:
            instance.quit.set()
            thread.join(timeout=3)
        self.assertFalse(thread.is_alive())


if __name__ == '__main__':
    unittest.main()
