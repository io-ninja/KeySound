#!/usr/bin/env python3
"""KeySound: local keyboard sounds for macOS and Windows."""
import argparse
import copy
import ctypes
import hashlib
import json
import math
import os
import queue
import re
import signal
import sys
import tempfile
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit
from contextlib import nullcontext

BASE = Path(__file__).resolve().parent
KEYS = dict(zip(
    [0,1,2,3,4,5,6,7,8,9,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31,32,33,34,35,36,37,38,39,40,41,42,43,44,45,46,47,48,49,50,51,53,54,55,56,57,58,59,60,61,62,63,64,65,67,69,71,75,76,78,81,82,83,84,85,86,87,88,89,91,92,96,97,98,99,100,101,103,105,106,107,109,111,114,115,116,117,118,119,120,121,122,123,124,125,126],
    ['A','S','D','F','H','G','Z','X','C','V','B','Q','W','E','R','Y','T','1','2','3','4','6','5','=','9','7','-','8','0',']','O','U','[','I','P','Enter','L','J',"'",'K',';','\\',',','/','N','M','.','Tab','Space','`','Backspace','Esc','Cmd kanan','Cmd','Shift','Caps Lock','Option','Control','Shift kanan','Option kanan','Control kanan','Fn','F17','Numpad .','Numpad *','Numpad +','Clear','Numpad /','Numpad Enter','Numpad -','Numpad =','Numpad 0','Numpad 1','Numpad 2','Numpad 3','Numpad 4','Numpad 5','Numpad 6','Numpad 7','Numpad 8','Numpad 9','F5','F6','F7','F3','F8','F9','F11','F13','F16','F14','F10','F12','Help','Home','Page Up','Delete','F4','End','F2','Page Down','F1','Left','Right','Down','Up'], strict=True))


DEFAULT_CONFIG = {"enabled": False, "pack": "gunshot", "mode": "single",
                  "volume": 0.25, "debounce_ms": 12, "max_voices": 4,
                  "overrides": {}, "default_sound": {}}


def load_config(path):
    if not path.exists():
        return json.loads(json.dumps(DEFAULT_CONFIG))
    config = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError("Konfigurasi harus berupa objek JSON.")
    if type(config.get("enabled", False)) is not bool:
        raise ValueError("enabled harus boolean.")
    config = {**copy.deepcopy(DEFAULT_CONFIG), **config}
    validate_config(config)
    return config


def validate_config(config, packs=None):
    if set(config) != set(DEFAULT_CONFIG) or type(config["enabled"]) is not bool:
        raise ValueError("Field konfigurasi tidak dikenal atau enabled bukan boolean.")
    if config["mode"] not in ("single", "per-key"):
        raise ValueError("Mode harus single atau per-key.")
    for field, low, high in [("volume", 0, 1), ("debounce_ms", 0, 200), ("max_voices", 1, 8)]:
        value = config[field]
        if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
            raise ValueError(f"{field} harus berupa angka {low} sampai {high}.")
        if field != "volume" and type(value) is not int:
            raise ValueError(f"{field} harus bilangan bulat.")
    if not isinstance(config["pack"], str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", config["pack"]):
        raise ValueError("ID pack tidak sah.")
    for field in ("overrides", "default_sound"):
        if not isinstance(config[field], dict) or len(config[field]) > 32:
            raise ValueError("Mapping konfigurasi tidak sah.")
        for pack_id, value in config[field].items():
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", pack_id):
                raise ValueError("ID mapping pack tidak sah.")
            mappings = value if field == "overrides" else {"0": value}
            if not isinstance(mappings, dict) or len(mappings) > len(KEYS):
                raise ValueError("Mapping tombol tidak sah.")
            for key, sound in mappings.items():
                if key not in {str(k) for k in KEYS} or not isinstance(sound, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 _.-]{0,95}\.(?:wav|mp3)", sound, re.I) or ".." in sound:
                    raise ValueError("Mapping berisi tombol/nama audio tidak sah.")
                if packs is not None and pack_id in packs and sound not in packs[pack_id]["files"]:
                    raise ValueError("Audio mapping tidak ditemukan dalam pack.")
    if packs is not None and (config["pack"] not in packs or not packs[config["pack"]]["files"]):
        raise ValueError("Pack tidak ditemukan atau masih kosong. Unggah audio terlebih dahulu.")


def resolve_sound(config, pack, key):
    default = config["default_sound"].get(pack["id"], pack["default"])
    if config["mode"] == "single":
        return default
    overrides = config["overrides"].get(pack["id"], {})
    return overrides.get(str(key), pack["mapping"].get(str(key), default))


MAX_UPLOAD = 10 * 1024 * 1024


def validate_upload(name, data):
    import re
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 _.-]{0,95}\.(?:wav|mp3)", name, re.I) or ".." in name:
        raise ValueError("Nama harus sederhana, berakhiran .wav/.mp3, tanpa jalur direktori.")
    if not 12 <= len(data) <= MAX_UPLOAD:
        raise ValueError("Berkas kosong/terlalu pendek atau melebihi 10 MiB.")
    wav = data[:4] == b"RIFF" and data[8:12] == b"WAVE"
    mp3 = data[:3] == b"ID3" or (data[0] == 255 and data[1] & 224 == 224)
    if not (wav if name.lower().endswith(".wav") else mp3):
        raise ValueError("Isi berkas tidak cocok dengan format audio.")
    return name


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".keysound-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        Path(tmp).unlink(missing_ok=True)


def read_pack(directory):
    manifest = directory / "pack.json"
    if manifest.is_symlink() or directory.is_symlink():
        raise ValueError("Symlink pack tidak diizinkan.")
    if manifest.stat().st_size > 32768:
        raise ValueError("pack.json terlalu besar.")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("name"), str):
        raise ValueError("Pack harus memiliki name.")
    files = sorted(p.name for p in directory.iterdir() if p.suffix.lower() in (".wav", ".mp3") and p.is_file())
    if len(files) > 16:
        raise ValueError("Maksimal 16 audio per pack.")
    for name in files:
        path = directory / name
        if path.is_symlink() or path.stat().st_size > MAX_UPLOAD:
            raise ValueError("Audio berupa symlink atau melebihi 10 MiB.")
        validate_upload(name, path.read_bytes())
    default = data.get("default")
    if default not in files and not (directory.name == "custom" and not files and default is None):
        raise ValueError("Suara default pack tidak ditemukan.")
    mapping = data.get("mapping", {})
    if not isinstance(mapping, dict) or any(key not in {str(k) for k in KEYS} or sound not in files for key, sound in mapping.items()):
        raise ValueError("Mapping pack berisi key atau nama audio yang tidak sah.")
    source = data.get("source", "Sumber audio belum dicantumkan oleh pembuat pack.")
    if not isinstance(source, str) or len(source) > 1000 or not 1 <= len(data["name"]) <= 80:
        raise ValueError("Nama/sumber pack terlalu panjang atau tidak sah.")
    return {"id": directory.name, "name": data["name"], "default": default,
            "mapping": mapping, "files": files, "source": source, "directory": directory}


def decode_audio(path):
    import AVFoundation as AV
    from Foundation import NSURL
    audio, error = AV.AVAudioFile.alloc().initForReading_error_(NSURL.fileURLWithPath_(str(path)), None)
    if audio is None:
        raise ValueError("Audio tidak dapat didekode. Gunakan WAV PCM atau MP3 yang valid.")
    fmt, frames = audio.processingFormat(), audio.length()
    rate, channels = fmt.sampleRate(), fmt.channelCount()
    if not 8000 <= rate <= 192000 or not 1 <= channels <= 2 or not 0 < frames <= rate * 10:
        raise ValueError("Audio harus mono/stereo, 8–192 kHz, berdurasi maksimal 10 detik.")
    buffer = AV.AVAudioPCMBuffer.alloc().initWithPCMFormat_frameCapacity_(fmt, frames)
    ok, error = audio.readIntoBuffer_error_(buffer, None)
    if not ok or buffer.frameLength() != frames:
        raise ValueError("Audio terpotong atau gagal didekode seluruhnya.")
    return buffer


class Audio:
    def __init__(self, pack, max_voices, volume):
        import AVFoundation as AV
        self.engine = AV.AVAudioEngine.alloc().init()
        self.clips = {}
        self.max_voices = max_voices
        self.volume = volume
        self.voices = []
        try:
            buffers = {name: decode_audio(pack["directory"] / name) for name in pack["files"]}
            if sum(b.frameLength() * b.format().channelCount() * 4 for b in buffers.values()) > 64 * 1024 * 1024:
                raise ValueError("Total audio decoded melebihi 64 MiB per pack.")
            for name, buffer in buffers.items():
                nodes = []
                for _ in range(max_voices):
                    node = AV.AVAudioPlayerNode.alloc().init()
                    self.engine.attachNode_(node)
                    self.engine.connect_to_format_(node, self.engine.mainMixerNode(), buffer.format())
                    voice = {"node": node, "until": 0.0}
                    self.voices.append(voice)
                    nodes.append(voice)
                self.clips[name] = (buffer, nodes)
            self.set_volume(volume)
            self.engine.prepare()
            ok, error = self.engine.startAndReturnError_(None)
            if not ok:
                raise RuntimeError("Perangkat audio tidak dapat dimulai: " + str(error))
        except Exception:
            self.close()
            raise

    def set_volume(self, volume):
        self.volume = volume
        # ponytail: fixed headroom avoids clipping at the voice cap; no compressor needed.
        self.engine.mainMixerNode().setOutputVolume_(volume / self.max_voices)

    def is_running(self):
        return bool(self.engine.isRunning())

    def play(self, name):
        if not self.engine.isRunning():
            self.restart()
        now = time.monotonic()
        # ponytail: at most 16 clips × 8 nodes; scan is bounded, no voice-manager abstraction.
        if sum(v["until"] > now for v in self.voices) >= self.max_voices:
            return False
        buffer, nodes = self.clips[name]
        voice = next(v for v in nodes if v["until"] <= now)
        voice["node"].stop()
        voice["node"].scheduleBuffer_completionHandler_(buffer, None)
        voice["node"].play()
        voice["until"] = now + buffer.frameLength() / buffer.format().sampleRate() + 0.03
        return True

    def stop(self):
        for voice in self.voices:
            voice["node"].stop()
            voice["until"] = 0.0

    def close(self):
        self.stop()
        self.engine.stop()

    def restart(self):
        """Recreate engine and nodes after AVAudioEngine stops (e.g. Bluetooth device disconnect)."""
        import AVFoundation as AV
        self.engine.stop()
        self.engine = AV.AVAudioEngine.alloc().init()
        self.voices = []
        for name, (buffer, _) in self.clips.items():
            nodes = []
            for _ in range(self.max_voices):
                node = AV.AVAudioPlayerNode.alloc().init()
                self.engine.attachNode_(node)
                self.engine.connect_to_format_(node, self.engine.mainMixerNode(), buffer.format())
                voice = {"node": node, "until": 0.0}
                self.voices.append(voice)
                nodes.append(voice)
            self.clips[name] = (buffer, nodes)
        self.set_volume(self.volume)
        self.engine.prepare()
        ok, error = self.engine.startAndReturnError_(None)
        if not ok:
            raise RuntimeError("Perangkat audio tidak dapat dimulai: " + str(error))


if sys.platform == "win32":
    from windows_backend import Audio, decode_audio


def permissions():
    if sys.platform == "win32":
        return {"required": False, "accessibility": None, "input_monitoring": None}
    import Quartz as Q
    ax = ctypes.CDLL("/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices")
    ax.AXIsProcessTrusted.restype = ctypes.c_bool
    return {"accessibility": bool(ax.AXIsProcessTrusted()),
            "input_monitoring": bool(Q.CGPreflightListenEventAccess())}


class App:
    def __init__(self, root):
        self.root, self.config_path = root, root / "config.json"
        self.lock = threading.RLock()
        self.quit = threading.Event()
        self.events = queue.Queue(maxsize=16)
        self.generation, self.last_trigger = 0, 0.0
        self.listener_ready, self.listener_error = False, "Listener belum dimulai."
        self.audio, self.audio_error = None, ""
        self.listener_thread = None
        custom = root / "packs/custom"
        custom.mkdir(parents=True, exist_ok=True)
        if not (custom / "pack.json").exists():
            atomic_json(custom / "pack.json", {"name": "Custom", "default": None, "mapping": {},
                        "source": "Audio yang Anda unggah sendiri. Pastikan Anda memiliki hak penggunaannya."})
        self.packs = self.scan_packs()
        self.config = load_config(self.config_path)
        validate_config(self.config, self.packs)
        try:
            self.audio = Audio(self.packs[self.config["pack"]], self.config["max_voices"], self.config["volume"])
        except Exception as error:
            self.audio_error = str(error)
        if not self.config_path.exists():
            atomic_json(self.config_path, self.config)
        self.worker = threading.Thread(target=self.consume, name="keysound-audio", daemon=True)
        self.worker.start()

    def scan_packs(self):
        packs = {}
        for parent in (BASE / "packs", self.root / "packs"):
            for path in sorted(parent.iterdir()):
                if path.is_dir() and (path / "pack.json").exists():
                    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", path.name) or path.name in packs:
                        raise ValueError("ID pack tidak sah atau duplikat: " + path.name)
                    packs[path.name] = read_pack(path)
        return packs

    def state(self):
        with self.lock:
            return {"config": copy.deepcopy(self.config),
                    "packs": [{k: v for k, v in p.items() if k != "directory"} for p in self.packs.values()],
                    "platform": sys.platform,
                    "keys": [{"code": str(k), "label": ({55:"Win", 54:"Win kanan", 58:"Alt", 61:"Alt kanan", 71:"Num Lock"}.get(k, v) if sys.platform == "win32" else v)} for k, v in KEYS.items()],
                    "status": {"listener": self.listener_ready, "listener_error": self.listener_error,
                               "audio": bool(self.audio and self.audio.is_running()),
                               "audio_error": self.audio_error, "permissions": permissions()}}

    def update(self, patch, force=False):
        candidate = {**copy.deepcopy(self.config), **patch}
        packs = self.scan_packs() if force else self.packs
        validate_config(candidate, packs)
        replacement = None
        if force or self.audio is None or any(candidate[k] != self.config[k] for k in ("pack", "max_voices")):
            replacement = Audio(packs[candidate["pack"]], candidate["max_voices"], candidate["volume"])
        try:
            atomic_json(self.config_path, candidate)
        except Exception:
            if replacement:
                replacement.close()
            raise
        with self.lock:
            old = self.audio
            if replacement:
                self.audio = replacement
            self.audio.set_volume(candidate["volume"])
            self.config, self.packs = candidate, packs
            self.generation += 1
            self.last_trigger = 0.0
            self.audio_error = ""
            if not candidate["enabled"]:
                self.audio.stop()
            if replacement and old:
                old.close()
        return self.state()

    def trigger(self, code, repeat=False):
        now = time.monotonic()
        with self.lock:
            if repeat or not self.config["enabled"] or not self.audio or now - self.last_trigger < self.config["debounce_ms"] / 1000:
                return False
            sound = resolve_sound(self.config, self.packs[self.config["pack"]], code)
            try:
                # Only a sound name is queued. No key codes, characters or key history are retained.
                self.events.put_nowait((sound, self.generation, now))
            except queue.Full:
                return False
            self.last_trigger = now
        return True

    def consume(self):
        pool = nullcontext
        if sys.platform == "darwin":
            import objc
            pool = objc.autorelease_pool
        while not self.quit.is_set():
            try:
                sound, generation, created = self.events.get(timeout=0.2)
            except queue.Empty:
                continue
            with pool(), self.lock:
                if generation != self.generation or not self.config["enabled"] or time.monotonic() - created > 0.1:
                    continue
                try:
                    self.audio.play(sound)
                    self.audio_error = ""
                except Exception as error:
                    self.audio_error = str(error)

    def preview(self, sound):
        with self.lock:
            if not self.audio:
                raise ValueError(self.audio_error or "Audio belum siap.")
            if sound not in self.packs[self.config["pack"]]["files"]:
                raise ValueError("Pilih audio dari pack aktif.")
            try:
                played = self.audio.play(sound)
                self.audio_error = ""
                return {"played": played}
            except Exception as error:
                self.audio_error = str(error)
                raise

    def upload(self, name, data):
        validate_upload(name, data)
        custom = self.packs["custom"]
        if len(custom["files"]) >= 16:
            raise ValueError("Pack custom penuh (16 audio). Hapus berkas yang tidak dipakai secara manual.")
        directory = custom["directory"]
        final_name = Path(name).stem[:60] + "-" + uuid.uuid4().hex[:8] + Path(name).suffix.lower()
        target = directory / final_name
        fd, temporary = tempfile.mkstemp(suffix=Path(name).suffix.lower(), prefix=".upload-", dir=self.root)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
            decode_audio(Path(temporary))  # Reject signature-only fakes before publishing a file.
            os.replace(temporary, target)
            if custom["default"] is None:
                atomic_json(directory / "pack.json", {"name": custom["name"], "default": final_name,
                            "mapping": {}, "source": custom["source"]})
            if self.config["pack"] == "custom":
                self.update({}, force=True)
            else:
                self.packs = self.scan_packs()
        except Exception:
            target.unlink(missing_ok=True)
            if custom["default"] is None:
                atomic_json(directory / "pack.json", {"name": custom["name"], "default": None,
                            "mapping": {}, "source": custom["source"]})
            raise
        finally:
            Path(temporary).unlink(missing_ok=True)
        return self.state()

    def listen(self):
        if sys.platform == "win32":
            from windows_backend import listen
            return listen(self)
        import Quartz as Q
        import objc
        tap = None

        def callback(proxy, event_type, event, refcon):
            try:
                if event_type in (Q.kCGEventTapDisabledByTimeout, Q.kCGEventTapDisabledByUserInput):
                    Q.CGEventTapEnable(tap, True)
                    return event
                if not self.config["enabled"]:
                    return event
                code = Q.CGEventGetIntegerValueField(event, Q.kCGKeyboardEventKeycode)
                if event_type == Q.kCGEventFlagsChanged and not Q.CGEventSourceKeyState(Q.kCGEventSourceStateCombinedSessionState, code):
                    return event
                repeat = bool(Q.CGEventGetIntegerValueField(event, Q.kCGKeyboardEventAutorepeat))
                self.trigger(code, repeat)
            except Exception:
                self.listener_error = "Callback keyboard gagal. Matikan lalu jalankan ulang service."
            return event

        with objc.autorelease_pool():
            try:
                mask = (1 << Q.kCGEventKeyDown) | (1 << Q.kCGEventFlagsChanged)
                while not self.quit.is_set():
                    if tap is None:
                        tap = Q.CGEventTapCreate(Q.kCGSessionEventTap, Q.kCGHeadInsertEventTap,
                                               Q.kCGEventTapOptionListenOnly, mask, callback, None)
                        if tap is None:
                            self.listener_error = "Izin keyboard belum tersedia. Buka Privacy & Security > Input Monitoring / Accessibility, izinkan aplikasi peluncur atau Python, lalu coba lagi."
                            self.quit.wait(2)
                            continue
                        source = Q.CFMachPortCreateRunLoopSource(None, tap, 0)
                        Q.CFRunLoopAddSource(Q.CFRunLoopGetCurrent(), source, Q.kCFRunLoopCommonModes)
                        Q.CGEventTapEnable(tap, True)
                    self.listener_ready = bool(Q.CGEventTapIsEnabled(tap))
                    if self.listener_ready:
                        self.listener_error = ""
                    else:
                        self.listener_error = "Listener dinonaktifkan macOS. Periksa izin keyboard lalu jalankan ulang service."
                    Q.CFRunLoopRunInMode(Q.kCFRunLoopDefaultMode, 0.2, False)
            except Exception:
                self.listener_error = "Listener tidak dapat berjalan. Periksa izin macOS lalu jalankan ulang service."
            finally:
                self.listener_ready = False
                if tap:
                    Q.CGEventTapEnable(tap, False)
                    Q.CFMachPortInvalidate(tap)

    def start_listener(self):
        self.listener_thread = threading.Thread(target=self.listen, name="keysound-listener", daemon=True)
        self.listener_thread.start()

    def close(self):
        self.quit.set()
        self.worker.join(timeout=2)
        if self.listener_thread:
            self.listener_thread.join(timeout=2)
        with self.lock:
            if self.audio:
                self.audio.close()


def make_server(app, port):
    class Handler(BaseHTTPRequestHandler):
        server_version = "KeySound"

        def log_message(self, *_):
            pass

        def setup(self):
            super().setup()
            self.connection.settimeout(5)

        def respond(self, status, data, content_type="application/json; charset=utf-8"):
            import base64
            raw = json.dumps(data, ensure_ascii=False, allow_nan=False).encode() if isinstance(data, dict) else data
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            hashes = {tag: " ".join("'sha256-" + base64.b64encode(hashlib.sha256(x).digest()).decode() + "'" for x in re.findall(rb"<" + tag.encode() + rb">(.*?)</" + tag.encode() + rb">", raw, re.S)) for tag in ("script", "style")}
            self.send_header("Content-Security-Policy", "default-src 'none'; connect-src 'self'; script-src " + (hashes['script'] or "'none'") + "; style-src " + (hashes['style'] or "'none'") + "; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
            self.end_headers()
            self.wfile.write(raw)

        def valid_request(self, mutation=False):
            host = self.headers.get("Host", "")
            if host not in (f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"):
                self.respond(403, {"error": "Host ditolak. Gunakan alamat localhost dashboard."})
                return False
            origin = self.headers.get("Origin")
            if mutation and (self.headers.get("X-Keysound") != "1" or (origin is not None and origin != "http://" + host)):
                self.respond(403, {"error": "Permintaan lintas situs ditolak."})
                return False
            return True

        def do_GET(self):
            if not self.valid_request():
                return
            route = urlsplit(self.path).path
            if route == "/":
                try:
                    self.respond(200, (BASE / "dashboard.html").read_bytes(), "text/html; charset=utf-8")
                except OSError:
                    self.respond(500, {"error": "dashboard.html tidak ditemukan."})
            elif route == "/api/state":
                self.respond(200, app.state())
            else:
                self.respond(404, {"error": "Tidak ditemukan."})

        def do_POST(self):
            if not self.valid_request(True):
                return
            try:
                route = urlsplit(self.path).path
                limit = MAX_UPLOAD if route == "/api/upload" else 32768
                length = int(self.headers.get("Content-Length", "0"))
                if self.headers.get("Transfer-Encoding") or not 0 < length <= limit:
                    raise ValueError("Ukuran permintaan tidak sah atau terlalu besar.")
                raw = self.rfile.read(length)
                if len(raw) != length:
                    raise ValueError("Unggahan terputus. Coba lagi.")
                if route == "/api/upload":
                    result = app.upload(unquote(self.headers.get("X-Filename", "")), raw)
                else:
                    if self.headers.get_content_type() != "application/json":
                        raise ValueError("Content-Type harus application/json.")
                    data = json.loads(raw)
                    if not isinstance(data, dict):
                        raise ValueError("Permintaan harus objek JSON.")
                    if route == "/api/config":
                        if set(data) - {"enabled", "pack", "mode", "volume", "debounce_ms", "max_voices"}:
                            raise ValueError("Field tidak dikenal.")
                        result = app.update(data)
                    elif route == "/api/mapping":
                        key, sound = data.get("key"), data.get("sound")
                        if key not in {str(k) for k in KEYS}:
                            raise ValueError("Pilih tombol yang sah.")
                        overrides = copy.deepcopy(app.config["overrides"])
                        mapping = overrides.setdefault(app.config["pack"], {})
                        if sound == "":
                            mapping.pop(key, None)
                        else:
                            mapping[key] = sound
                        result = app.update({"overrides": overrides})
                    elif route == "/api/default":
                        defaults = {**app.config["default_sound"], app.config["pack"]: data.get("sound")}
                        result = app.update({"default_sound": defaults})
                    elif route == "/api/preview":
                        result = app.preview(data.get("sound"))
                    elif route == "/api/reload":
                        result = app.update({}, force=True)
                    else:
                        self.respond(404, {"error": "Tidak ditemukan."})
                        return
                self.respond(200, result)
            except (ValueError, TypeError, KeyError) as error:
                self.respond(400, {"error": str(error)})
            except (OSError, RuntimeError) as error:
                self.respond(503, {"error": str(error)})
            except Exception:
                self.respond(500, {"error": "Operasi gagal. Periksa audio dan akses keyboard, lalu coba lagi."})
    return HTTPServer(("127.0.0.1", port), Handler)


def selftest():
    with tempfile.TemporaryDirectory(prefix="keysound-test-") as directory:
        path = Path(directory) / "config.json"
        config = load_config(path)
        assert config["enabled"] is False, "First run must not listen without opt-in"
        assert config["pack"] == "gunshot"
        atomic_json(path, {**config, "volume": 0.4})
        assert load_config(path)["volume"] == 0.4
        for patch in ({"volume": True}, {"volume": float("nan")}, {"volume": 1.1},
                      {"max_voices": 9}, {"max_voices": 1.5}, {"debounce_ms": -1},
                      {"pack": "../escape"}, {"mode": "invalid"}, {"unknown": 1},
                      {"overrides": {"gunshot": {"999": "gunshot.wav"}}}):
            try:
                validate_config({**config, **patch})
            except ValueError:
                pass
            else:
                raise AssertionError("Invalid configuration accepted")
        path.write_text('{"enabled": "yes"}')
        try:
            load_config(path)
        except ValueError:
            pass
        else:
            raise AssertionError("Invalid configuration must not be accepted")
    print("PASS: configuration defaults, persistence and invalid types")
    config = json.loads(json.dumps(DEFAULT_CONFIG))
    pack = {"id": "gunshot", "default": "gunshot.wav", "mapping": {"36": "enter.wav"},
            "files": ["gunshot.wav", "enter.wav"]}
    assert resolve_sound(config, pack, "36") == "gunshot.wav"
    config["mode"] = "per-key"
    assert resolve_sound(config, pack, "36") == "enter.wav"
    assert resolve_sound(config, pack, "49") == "gunshot.wav"
    config["overrides"] = {"gunshot": {"36": "gunshot.wav"}}
    assert resolve_sound(config, pack, "36") == "gunshot.wav"
    print("PASS: single, per-key, overrides and fallback")
    assert validate_upload("sound.wav", b"RIFF" + b"\0" * 4 + b"WAVE" + b"\0" * 32) == "sound.wav"
    assert validate_upload("sound.mp3", b"ID3" + b"\0" * 40) == "sound.mp3"
    for name, data in [("../evil.wav", b"RIFF"), ("..\\evil.wav", b"RIFF"),
                       ("/evil.wav", b"RIFF"), ("%2e%2e.wav", b"RIFF"),
                       ("bad.html", b"<html>"), ("fake.wav", b"not audio"),
                       ("empty.mp3", b""), ("big.wav", b"x" * (10 * 1024 * 1024 + 1))]:
        try:
            validate_upload(name, data)
        except ValueError:
            pass
        else:
            raise AssertionError("Unsafe upload accepted: " + name)
    print("PASS: upload names, traversal, format, empty and size limits")


def default_config_dir():
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "KeySound"
    return Path.home() / ".config/keysound"


def main():
    parser = argparse.ArgumentParser(description="Keyboard sounds + localhost dashboard for macOS and Windows")
    parser.add_argument("--selftest", action="store_true", help="Run stdlib-only checks without listening or playing audio")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--config-dir", type=Path, default=default_config_dir())
    parser.add_argument("--log-file", type=Path, help="Startup/error log for background launch; never logs keystrokes")
    args = parser.parse_args()
    if args.selftest:
        selftest()
        return
    if sys.platform not in ("darwin", "win32"):
        parser.error("Service mendukung macOS dan Windows. --selftest tetap tersedia di platform lain.")
    if args.log_file:
        args.log_file.parent.mkdir(parents=True, exist_ok=True)
        sys.stdout = sys.stderr = args.log_file.open("a", encoding="utf-8", buffering=1)
    if not 1024 <= args.port <= 65535:
        parser.error("Port harus 1024–65535.")
    try:
        if sys.platform == "darwin":
            import Quartz
            import AVFoundation
        else:
            import pynput
            import sounddevice
            import soundfile
            import numpy
    except ImportError:
        parser.error("Dependency belum tersedia. Jalankan python -m pip install -r requirements.txt dalam .venv proyek.")
    app = None
    server = None
    try:
        app = App(args.config_dir.expanduser().resolve())
        server = make_server(app, args.port)
        app.start_listener()
        def stop(signum, frame):
            raise KeyboardInterrupt
        signal.signal(signal.SIGTERM, stop)
        print(f"KeySound dashboard: http://127.0.0.1:{args.port}", flush=True)
        print("Suara " + ("aktif." if app.config["enabled"] else "dimatikan. Aktifkan dari dashboard."), flush=True)
        if sys.platform == "darwin":
            print("Jika listener belum siap: System Settings > Privacy & Security > Input Monitoring / Accessibility.", flush=True)
        else:
            print("Jalankan pada sesi desktop pengguna. Windows Service/layar UAC tidak didukung.", flush=True)
        if app.audio_error:
            print("Audio: " + app.audio_error, file=sys.stderr, flush=True)
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        print("KeySound dihentikan.", flush=True)
    except (OSError, ValueError) as error:
        print("KeySound gagal dimulai: " + str(error), file=sys.stderr)
        raise SystemExit(1)
    finally:
        if server:
            server.server_close()
        if app:
            app.close()


if __name__ == "__main__":
    main()
