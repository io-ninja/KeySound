"""Windows input and preloaded audio; canonical IDs preserve existing mappings."""
import threading
import time


def decode_audio(path):
    import numpy as np
    import soundfile as sf
    try:
        with sf.SoundFile(str(path)) as source:
            rate, channels, frames = source.samplerate, source.channels, source.frames
            if not 8000 <= rate <= 192000 or not 1 <= channels <= 2 or not 0 < frames <= rate * 10:
                raise ValueError("Audio harus mono/stereo, 8–192 kHz, berdurasi maksimal 10 detik.")
            data = source.read(frames, dtype='float32', always_2d=True)
    except (sf.LibsndfileError, OSError) as error:
        raise ValueError("Audio tidak dapat didekode. Gunakan WAV/MP3 yang valid.") from error
    if len(data) != frames or not np.isfinite(data).all():
        raise ValueError("Audio terpotong atau berisi sampel tidak sah.")
    np.clip(data, -1, 1, out=data)
    return data, rate


def convert_audio(data, source_rate, target_rate, channels):
    import numpy as np
    if data.shape[1] != channels:
        data = np.repeat(data, 2, axis=1) if channels == 2 else data.mean(axis=1, keepdims=True)
    if source_rate != target_rate:
        count = max(1, round(len(data) * target_rate / source_rate))
        # ponytail: linear interpolation for short SFX; use a bandlimited converter for music.
        positions = np.arange(count) * source_rate / target_rate
        data = np.column_stack([np.interp(positions, np.arange(len(data)), data[:, channel])
                                for channel in range(channels)])
    return np.ascontiguousarray(data, dtype='float32')


class Audio:
    def __init__(self, pack, max_voices, volume):
        self.max_voices, self.volume = max_voices, volume
        self.lock = threading.Lock()
        self.voices = [None] * max_voices
        self.stream = None
        self.buffers, self.clips = {}, {}
        self.next_retry = 0.0
        total = 0
        for name in pack['files']:
            decoded = decode_audio(pack['directory'] / name)
            total += decoded[0].nbytes
            if total > 64 * 1024 * 1024:
                raise ValueError('Total audio decoded melebihi 64 MiB.')
            self.clips[name] = decoded
        try:
            self._open_stream()
        except Exception:
            self.close()
            raise

    def _open_stream(self):
        import sounddevice as sd
        device = sd.query_devices(kind='output')
        rate = round(device['default_samplerate'])
        channels = min(2, device['max_output_channels'])
        if not 8000 <= rate <= 192000 or channels < 1:
            raise RuntimeError('Output audio Windows tidak tersedia. Pilih perangkat output lalu muat ulang audio.')
        buffers = {}
        total = sum(data.nbytes for data, _ in self.clips.values())
        for name, (data, source_rate) in self.clips.items():
            buffers[name] = convert_audio(data, source_rate, rate, channels)
            total += buffers[name].nbytes
            if total > 64 * 1024 * 1024:
                raise ValueError('Buffer sumber dan output melebihi 64 MiB.')
        self.buffers = buffers
        self.stream = sd.OutputStream(samplerate=rate, channels=channels, dtype='float32',
                                      latency='low', blocksize=0, callback=self._render)
        self.stream.start()

    def is_running(self):
        return bool(self.stream is not None and self.stream.active)

    def _render(self, output, frames, timing, status):
        import numpy as np
        output.fill(0)
        # ponytail: at most eight voices; never wait for the control thread in an audio callback.
        if not self.lock.acquire(blocking=False):
            return
        try:
            for index, voice in enumerate(self.voices):
                if voice is None:
                    continue
                data, position = voice
                count = min(frames, len(data) - position)
                output[:count] += data[position:position + count]
                voice[1] += count
                if voice[1] == len(data):
                    self.voices[index] = None
            output *= self.volume / self.max_voices
            np.clip(output, -1, 1, out=output)
        finally:
            self.lock.release()

    def set_volume(self, volume):
        with self.lock:
            self.volume = volume

    def play(self, name):
        if not self.is_running():
            if time.monotonic() < self.next_retry:
                raise RuntimeError('Output belum tersedia. Periksa perangkat audio lalu coba lagi.')
            self.next_retry = time.monotonic() + 2
            self.close()
            try:
                self._open_stream()
            except Exception as error:
                self.close()
                raise RuntimeError('Tidak dapat memulai output audio: ' + str(error)) from error
        with self.lock:
            try:
                index = self.voices.index(None)
            except ValueError:
                return False
            self.voices[index] = [self.buffers[name], 0]
            return True

    def stop(self):
        with self.lock:
            self.voices[:] = [None] * self.max_voices

    def close(self):
        self.stop()
        if self.stream is not None:
            self.stream.close()
            self.stream = None


def listen(app):
    from pynput import keyboard
    held = set()

    def event_filter(message, data):
        if not app.config['enabled']:
            held.clear()
            return False
        code = key_event(message, data.scanCode, data.flags, held)
        if code is not None and app.lock.acquire(blocking=False):
            try:
                app.trigger(code)
            finally:
                app.lock.release()
        # False skips pynput's character conversion/callbacks, NOT the OS event.
        return False

    listener = keyboard.Listener(win32_event_filter=event_filter, suppress=False)
    try:
        listener.start()
        listener.wait()
        app.listener_ready = listener.is_alive()
        app.listener_error = '' if app.listener_ready else 'Listener Windows gagal dimulai.'
        while not app.quit.wait(0.2):
            if not listener.is_alive():
                raise RuntimeError('Listener Windows berhenti. Jalankan ulang KeySound.')
    except Exception:
        app.listener_error = 'Listener Windows gagal. Jalankan di sesi desktop pengguna, bukan Windows Service.'
    finally:
        app.listener_ready = False
        listener.stop()
        listener.join(timeout=1)
        held.clear()


# Set-1 physical scan codes -> existing KeySound IDs (not Windows virtual keys).
SCAN_KEYS = {
    0x01:53, 0x02:18, 0x03:19, 0x04:20, 0x05:21, 0x06:23, 0x07:22,
    0x08:26, 0x09:28, 0x0a:25, 0x0b:29, 0x0c:27, 0x0d:24, 0x0e:51,
    0x0f:48, 0x10:12, 0x11:13, 0x12:14, 0x13:15, 0x14:17, 0x15:16,
    0x16:32, 0x17:34, 0x18:31, 0x19:35, 0x1a:33, 0x1b:30, 0x1c:36,
    0x1d:59, 0x1e:0, 0x1f:1, 0x20:2, 0x21:3, 0x22:5, 0x23:4,
    0x24:38, 0x25:40, 0x26:37, 0x27:41, 0x28:39, 0x29:50, 0x2a:56,
    0x2b:42, 0x2c:6, 0x2d:7, 0x2e:8, 0x2f:9, 0x30:11, 0x31:45,
    0x32:46, 0x33:43, 0x34:47, 0x35:44, 0x36:60, 0x37:67, 0x38:58,
    0x39:49, 0x3a:57, 0x3b:122, 0x3c:120, 0x3d:99, 0x3e:118,
    0x3f:96, 0x40:97, 0x41:98, 0x42:100, 0x43:101, 0x44:109,
    0x45:71, 0x47:89, 0x48:91, 0x49:92, 0x4a:78, 0x4b:86,
    0x4c:87, 0x4d:88, 0x4e:69, 0x4f:83, 0x50:84, 0x51:85,
    0x52:82, 0x53:65, 0x57:103, 0x58:111, 0x64:105, 0x65:107, 0x67:106, 0x68:64,
}
EXTENDED_KEYS = {0x1c:76, 0x1d:62, 0x35:75, 0x38:61, 0x47:115,
                 0x48:126, 0x49:116, 0x4b:123, 0x4d:124, 0x4f:119,
                 0x50:125, 0x51:121, 0x53:117, 0x5b:55, 0x5c:54}


def key_event(message, scan, flags, held):
    identity = (scan, bool(flags & 1))
    if message in (0x101, 0x105):  # WM_KEYUP / WM_SYSKEYUP
        held.discard(identity)
        return None
    if message not in (0x100, 0x104) or identity in held or not 0 <= scan <= 255:
        return None
    held.add(identity)
    return (EXTENDED_KEYS if identity[1] else SCAN_KEYS).get(scan, -1)
