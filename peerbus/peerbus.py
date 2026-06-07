"""
peerbus daemon — Peer RPC Infrastructure

Singleton background process per account.
- NFS presence management (heartbeat, polling)
- NFS message queue management (offline delivery fallback)
- TCP peer communication (daemon-to-daemon P2P, E2EE)
- REST API server (Unix domain socket ~/.config/skillup/peerbus/daemon.sock)

Run directly: python peerbus/peerbus.py --uid <uid> --nfs-dir <path>
"""

import asyncio
import base64
import collections
import configparser
import json
import logging
import os
import signal
import socket
import socketserver
import struct
import sys
import time
import uuid
from http.server import BaseHTTPRequestHandler
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import nacl.encoding
import nacl.hash
import nacl.public
import nacl.secret
import nacl.signing
import nacl.utils

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# TCP port range used if OS assignment somehow blocked by firewall rules
PEERBUS_EXTERNAL_TCP_PORT_RANGE = (17431, 17530)

PRESENCE_HEARTBEAT_INTERVAL = 60     # seconds
PRESENCE_OFFLINE_TIMEOUT    = 600    # 10 minutes without heartbeat -> offline
QUEUE_TTL                   = 72 * 3600   # 72 hours
IDLE_TCP_TIMEOUT            = 300    # seconds before closing idle TCP connection
HANDSHAKE_TS_TOLERANCE      = 60     # seconds for replay prevention in TCP handshake
NFS_QUEUE_TS_TOLERANCE      = 300    # seconds for NFS queue msg replay prevention
BUILD_POLL_INTERVAL         = 60     # seconds
NFS_QUEUE_POLL_INTERVAL     = 60     # seconds — periodic re-check of own drop dir
DELIVERY_CB_TIMEOUT         = 2      # seconds for desktop callback HTTP call
DELIVERY_PARK_TIMEOUT       = 30     # seconds before retrying parked messages

DAEMON_VERSION = 1

# (uid, ip) tuple type alias
PeerKey = Tuple[str, str]


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [peerbus] %(levelname)s %(message)s',
    stream=sys.stderr,
)
logger = logging.getLogger('peerbus')

_LOG_MAX_BYTES = 512 * 1024  # 512 KB


def _setup_file_logging(log_dir: str, uid: str) -> None:
    os.makedirs(log_dir, mode=0o777, exist_ok=True)
    try:
        os.chmod(log_dir, 0o777)
    except OSError:
        pass

    log_path = os.path.join(log_dir, f'{uid}.log')

    class _RotatingFileHandler(logging.StreamHandler):
        def __init__(self, path: str, max_bytes: int):
            self._path = path
            self._max_bytes = max_bytes
            self._file = open(path, 'a', encoding='utf-8')  # noqa: SIM115
            super().__init__(self._file)

        def emit(self, record):
            try:
                if self._file.tell() >= self._max_bytes:
                    self._file.close()
                    old_path = self._path + '.old'
                    try:
                        os.replace(self._path, old_path)
                    except OSError:
                        pass
                    self._file = open(self._path, 'a', encoding='utf-8')  # noqa: SIM115
                    self.stream = self._file
            except OSError:
                pass
            super().emit(record)

    handler = _RotatingFileHandler(log_path, _LOG_MAX_BYTES)
    handler.setFormatter(logging.Formatter(
        '%(asctime)s [peerbus] %(levelname)s %(message)s'
    ))
    logger.addHandler(handler)


# ---------------------------------------------------------------------------
# Key material helpers
# ---------------------------------------------------------------------------

def _b64enc(data: bytes) -> str:
    return base64.b64encode(data).decode()

def _b64dec(s: str) -> bytes:
    return base64.b64decode(s)


def _load_or_create_identity(key_dir: str) -> tuple:
    """Return (enc_privkey, sign_privkey). Create and persist if absent."""
    os.makedirs(key_dir, exist_ok=True)
    enc_path  = os.path.join(key_dir, 'enc.key')
    sign_path = os.path.join(key_dir, 'sign.key')

    if os.path.exists(enc_path) and os.path.exists(sign_path):
        with open(enc_path, 'rb') as f:
            enc_priv = nacl.public.PrivateKey(f.read())
        with open(sign_path, 'rb') as f:
            sign_priv = nacl.signing.SigningKey(f.read())
    else:
        enc_priv  = nacl.public.PrivateKey.generate()
        sign_priv = nacl.signing.SigningKey.generate()
        with open(enc_path, 'wb') as f:
            f.write(bytes(enc_priv))
        with open(sign_path, 'wb') as f:
            f.write(bytes(sign_priv))
        os.chmod(enc_path, 0o600)
        os.chmod(sign_path, 0o600)

    return enc_priv, sign_priv


def _pubkey_fingerprint(enc_pub: nacl.public.PublicKey) -> str:
    raw = bytes(enc_pub)
    digest = nacl.hash.blake2b(raw, encoder=nacl.encoding.RawEncoder)
    return base64.b64encode(digest[:16]).decode()


# ---------------------------------------------------------------------------
# NFS helpers
# ---------------------------------------------------------------------------

def _atomic_write(path: str, data: bytes) -> None:
    """Write data to path via tmp+rename for NFS atomicity."""
    tmp = path + '.tmp'
    with open(tmp, 'wb') as f:
        f.write(data)
    os.replace(tmp, path)


def _get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'


# ---------------------------------------------------------------------------
# TCP frame codec
# ---------------------------------------------------------------------------

def _encode_frame(data: bytes) -> bytes:
    return struct.pack('>I', len(data)) + data

async def _read_frame(reader: asyncio.StreamReader) -> bytes:
    hdr = await reader.readexactly(4)
    length = struct.unpack('>I', hdr)[0]
    return await reader.readexactly(length)


# ---------------------------------------------------------------------------
# Session encryption
# ---------------------------------------------------------------------------

def _derive_session_key(shared_secret: bytes, uid_a: str, uid_b: str) -> bytes:
    peers = sorted([uid_a.encode(), uid_b.encode()])
    material = shared_secret + peers[0] + b'||' + peers[1]
    return nacl.hash.blake2b(material, digest_size=32, encoder=nacl.encoding.RawEncoder)


def _encrypt(session_key: bytes, plaintext: bytes) -> bytes:
    nonce = nacl.utils.random(nacl.secret.SecretBox.NONCE_SIZE)
    box   = nacl.secret.SecretBox(session_key)
    ct    = box.encrypt(plaintext, nonce).ciphertext
    return nonce + ct


def _decrypt(session_key: bytes, payload: bytes) -> bytes:
    nonce_size = nacl.secret.SecretBox.NONCE_SIZE
    nonce = payload[:nonce_size]
    ct    = payload[nonce_size:]
    box   = nacl.secret.SecretBox(session_key)
    return box.decrypt(ct, nonce)


# ---------------------------------------------------------------------------
# Message priority queue
# ---------------------------------------------------------------------------

class MessageQueue:
    """In-memory priority queue. sendmessage -> urgent (deque left), postmessage -> normal."""

    def __init__(self):
        self._q: collections.deque = collections.deque()
        self._event = asyncio.Event()

    def enqueue(self, item: dict) -> None:
        if item.get('msg_type') == 'sendmessage':
            self._q.appendleft(item)
        else:
            self._q.append(item)
        self._event.set()

    def dequeue(self) -> Optional[dict]:
        if self._q:
            item = self._q.popleft()
            if not self._q:
                self._event.clear()
            return item
        return None

    async def wait(self) -> None:
        await self._event.wait()

    def __len__(self) -> int:
        return len(self._q)


# ---------------------------------------------------------------------------
# Pending send tracker
# ---------------------------------------------------------------------------

class PendingSend:
    def __init__(self, send_id: str, wait_for: str):
        self.send_id  = send_id
        self.wait_for = wait_for
        self.future: asyncio.Future = asyncio.get_running_loop().create_future()


# ---------------------------------------------------------------------------
# Unix domain socket HTTP server
# ---------------------------------------------------------------------------

class _UnixSocketHTTPServer(socketserver.UnixStreamServer):
    """HTTP server bound to a Unix domain socket."""

    allow_reuse_address = True

    def server_bind(self):
        super().server_bind()
        os.chmod(self.server_address, 0o600)

    def get_request(self):
        request, client_address = super().get_request()
        # BaseHTTPRequestHandler expects a (conn, addr) tuple where addr is a string
        return request, ('unix', 0)


# ---------------------------------------------------------------------------
# PeerbusDaemon
# ---------------------------------------------------------------------------

class PeerbusDaemon:
    """daemon process body. singleton per account."""

    def __init__(self, uid: str, nfs_dir: str, skillup_root: str):
        self.uid         = uid
        self.nfs_dir     = nfs_dir
        self.skillup_root = skillup_root

        from lib.config import get_config_home
        config_home  = get_config_home()
        self._pid_path  = os.path.join(config_home, 'peerbus', 'daemon.pid')
        self._sock_path = os.path.join(config_home, 'peerbus', 'daemon.sock')
        self._key_dir   = os.path.join(config_home, 'peerbus')

        self._local_ip: str = _get_local_ip()
        self._tcp_port: int = 0  # assigned after asyncio.start_server

        self._enc_priv, self._sign_priv = _load_or_create_identity(self._key_dir)
        self._enc_pub   = self._enc_priv.public_key
        self._sign_pub  = self._sign_priv.verify_key

        # peer state: (uid, ip) -> {uid, ip, tcp_port, pubkey_fp, ts, online}
        self._peers: Dict[PeerKey, dict] = {}
        # uid -> {enc_pub, sign_pub, ...} — identity is per account, not per PC
        self._peer_pubkeys: Dict[str, dict] = {}
        self._mtime_cache: Dict[str, float] = {}

        # registered desktops: desktop_id -> {app_id, callback_port}
        self._desktops: Dict[str, dict] = {}

        # in-memory message queue (incoming, to be delivered to desktops)
        self._inbox = MessageQueue()
        # command_exec messages bypass the desktop delivery queue entirely
        self._cmd_queue = MessageQueue()
        # initialized in _run() after event loop is running
        self._desktop_registered: Optional[asyncio.Event] = None

        # send_id -> PendingSend (outgoing, waiting for status)
        self._pending: Dict[str, PendingSend] = {}

        # active TCP sessions: (uid, ip) -> (reader, writer, session_key)
        self._sessions: Dict[PeerKey, tuple] = {}
        self._session_last_used: Dict[PeerKey, float] = {}

        # dedup set for received send_ids
        self._seen_send_ids: set = set()

        # build tracking
        self._last_build: Optional[int] = None
        self._buildinfo_path = os.path.join(skillup_root, 'buildinfo.ini')
        self._buildinfo_mtime: Optional[float] = None

        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._start_time = time.time()

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------

    def start(self) -> None:
        self._write_pid()
        self._bootstrap_nfs_dirs()
        self._publish_identity()
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._run())
        except RuntimeError as e:
            # "Event loop stopped before Future completed" on SIGTERM — expected
            if 'Event loop stopped' not in str(e):
                raise
        finally:
            self._cleanup()

    def stop(self) -> None:
        if self._loop:
            self._loop.call_soon_threadsafe(self._loop.stop)

    # ------------------------------------------------------------------
    # Singleton / PID
    # ------------------------------------------------------------------

    def _write_pid(self) -> None:
        os.makedirs(os.path.dirname(self._pid_path), exist_ok=True)
        with open(self._pid_path, 'w') as f:
            f.write(str(os.getpid()))

    def _cleanup(self) -> None:
        try:
            os.unlink(self._pid_path)
        except OSError:
            pass
        try:
            os.unlink(self._sock_path)
        except OSError:
            pass
        self._remove_presence()

    # ------------------------------------------------------------------
    # NFS directory bootstrap
    # ------------------------------------------------------------------

    def _bootstrap_nfs_dirs(self) -> None:
        presence_dir = os.path.join(self.nfs_dir, 'presence')
        identity_dir = os.path.join(self.nfs_dir, 'identity')
        queue_dir    = os.path.join(self.nfs_dir, 'queue')
        log_dir      = os.path.join(self.nfs_dir, 'log')

        for d, mode in [(presence_dir, 0o777), (identity_dir, 0o777),
                        (queue_dir, 0o777), (log_dir, 0o777)]:
            os.makedirs(d, exist_ok=True)
            try:
                os.chmod(d, mode)
            except OSError:
                pass

        _setup_file_logging(log_dir, self.uid)

        my_queue  = os.path.join(queue_dir, self.uid)
        my_drop   = os.path.join(my_queue, 'drop')
        for d, mode in [(my_queue, 0o711), (my_drop, 0o733)]:
            os.makedirs(d, exist_ok=True)
            try:
                os.chmod(d, mode)
            except OSError:
                pass

    # ------------------------------------------------------------------
    # Identity / NFS
    # ------------------------------------------------------------------

    def _publish_identity(self) -> None:
        identity_dir = os.path.join(self.nfs_dir, 'identity')
        os.makedirs(identity_dir, exist_ok=True)

        enc_pub_b64  = _b64enc(bytes(self._enc_pub))
        sign_pub_b64 = _b64enc(bytes(self._sign_pub))
        ts           = int(time.time())

        sign_data = f"{self.uid}|{enc_pub_b64}|{sign_pub_b64}|{ts}".encode()
        sig       = _b64enc(bytes(self._sign_priv.sign(sign_data).signature))

        doc = {
            'uid':          self.uid,
            'pubkey_enc':   enc_pub_b64,
            'pubkey_sign':  sign_pub_b64,
            'ts':           ts,
            'sig':          sig,
        }
        path = os.path.join(identity_dir, f'{self.uid}.pub')
        _atomic_write(path, json.dumps(doc).encode())
        os.chmod(path, 0o644)

    def _load_peer_identity(self, uid: str) -> Optional[dict]:
        """Load and TOFU-verify peer's identity from NFS."""
        path = os.path.join(self.nfs_dir, 'identity', f'{uid}.pub')
        if not os.path.exists(path):
            return None
        try:
            doc = json.loads(open(path).read())
            enc_pub_b64  = doc['pubkey_enc']
            sign_pub_b64 = doc['pubkey_sign']
            ts           = doc['ts']

            sign_pub = nacl.signing.VerifyKey(_b64dec(sign_pub_b64))
            sign_data = f"{uid}|{enc_pub_b64}|{sign_pub_b64}|{ts}".encode()
            sig = _b64dec(doc['sig'])
            sign_pub.verify(sign_data, sig)

            cached = self._peer_pubkeys.get(uid)
            if cached and cached['sign_pub_b64'] != sign_pub_b64:
                logger.warning("TOFU key mismatch for %s — key has changed!", uid)

            self._peer_pubkeys[uid] = {
                'enc_pub':      nacl.public.PublicKey(_b64dec(enc_pub_b64)),
                'sign_pub':     sign_pub,
                'enc_pub_b64':  enc_pub_b64,
                'sign_pub_b64': sign_pub_b64,
            }
            return self._peer_pubkeys[uid]
        except Exception as e:
            logger.warning("Failed to load identity for %s: %s", uid, e)
            return None

    # ------------------------------------------------------------------
    # Presence
    # ------------------------------------------------------------------

    def _presence_filename(self, uid: Optional[str] = None,
                           ip: Optional[str] = None) -> str:
        u = uid if uid is not None else self.uid
        i = ip  if ip  is not None else self._local_ip
        return f'{u}@{i}.json'

    def _presence_path(self, uid: Optional[str] = None,
                       ip: Optional[str] = None) -> str:
        return os.path.join(self.nfs_dir, 'presence',
                            self._presence_filename(uid, ip))

    def _publish_presence(self) -> None:
        doc = {
            'uid':        self.uid,
            'ip':         self._local_ip,
            'tcp_port':   self._tcp_port,
            'pubkey_fp':  _pubkey_fingerprint(self._enc_pub),
            'ts':         int(time.time()),
        }
        path = self._presence_path()
        try:
            _atomic_write(path, json.dumps(doc).encode())
            os.chmod(path, 0o644)
        except Exception as e:
            logger.warning("Failed to publish presence: %s", e)

    def _remove_presence(self) -> None:
        try:
            os.unlink(self._presence_path())
        except OSError:
            pass

    def _poll_presence_one(self, uid: str, ip: str) -> dict:
        """Check presence for a single (uid, ip) pair directly without scandir."""
        path = self._presence_path(uid, ip)
        peer_key: PeerKey = (uid, ip)
        now = time.time()
        try:
            st = os.stat(path)
            mtime = st.st_mtime
            prev_mtime = self._mtime_cache.get(path)
            if mtime != prev_mtime:
                data = json.loads(open(path).read())
                self._mtime_cache[path] = mtime
                self._update_peer(data)
            if now - mtime > PRESENCE_OFFLINE_TIMEOUT:
                self._mark_offline(uid, ip)
        except FileNotFoundError:
            self._mark_offline(uid, ip)
        except Exception as e:
            logger.warning("poll_presence_one %s@%s failed: %s", uid, ip, e)
        return self._peers.get(peer_key, {'online': False, 'tcp_port': 0, 'ts': 0})

    def _poll_presence(self) -> None:
        presence_dir = os.path.join(self.nfs_dir, 'presence')
        now = time.time()
        before_online = sum(1 for info in self._peers.values() if info.get('online'))
        try:
            with os.scandir(presence_dir) as it:
                seen: set = set()
                for entry in it:
                    if not entry.name.endswith('.json'):
                        continue
                    stem = entry.name[:-5]  # remove .json
                    if '@' not in stem:
                        continue  # skip legacy <uid>.json files
                    uid, ip = stem.rsplit('@', 1)
                    peer_key: PeerKey = (uid, ip)
                    seen.add(peer_key)

                    try:
                        mtime = entry.stat(follow_symlinks=False).st_mtime
                    except OSError:
                        continue

                    prev_mtime = self._mtime_cache.get(entry.name)
                    if mtime != prev_mtime:
                        try:
                            data = json.loads(open(entry.path).read())
                            self._mtime_cache[entry.name] = mtime
                            self._update_peer(data)
                        except Exception:
                            pass
                    elif now - mtime > PRESENCE_OFFLINE_TIMEOUT:
                        # stale file from crashed peer
                        try:
                            os.unlink(entry.path)
                            self._mtime_cache.pop(entry.name, None)
                            self._mark_offline(uid, ip)
                        except OSError:
                            pass

                # peers whose file disappeared -> offline
                my_key: PeerKey = (self.uid, self._local_ip)
                for peer_key, info in list(self._peers.items()):
                    if peer_key != my_key and peer_key not in seen and info.get('online'):
                        self._mark_offline(*peer_key)
        except Exception as e:
            logger.warning("presence poll error: %s", e)
            return
        after_online = sum(1 for info in self._peers.values() if info.get('online'))
        if after_online != before_online:
            logger.info("presence poll: peers online %d -> %d", before_online, after_online)

    def _poll_presence_for_uid(self, uid: str) -> None:
        """Re-read presence files for a specific uid directly, bypassing mtime cache."""
        presence_dir = os.path.join(self.nfs_dir, 'presence')
        prefix = f'{uid}@'
        now = time.time()
        try:
            with os.scandir(presence_dir) as it:
                for entry in it:
                    if not entry.name.startswith(prefix) or not entry.name.endswith('.json'):
                        continue
                    try:
                        mtime = entry.stat(follow_symlinks=False).st_mtime
                        if now - mtime > PRESENCE_OFFLINE_TIMEOUT:
                            continue
                        data = json.loads(open(entry.path).read())
                        self._mtime_cache[entry.name] = mtime
                        self._update_peer(data)
                    except Exception as e:
                        logger.warning("poll_presence_for_uid %s entry error: %s", uid, e)
        except Exception as e:
            logger.warning("poll_presence_for_uid %s error: %s", uid, e)

    def _update_peer(self, data: dict) -> None:
        uid = data.get('uid')
        ip  = data.get('ip')
        if not uid or not ip:
            return
        # ignore our own presence entry
        if uid == self.uid and ip == self._local_ip:
            return
        peer_key: PeerKey = (uid, ip)
        prev = self._peers.get(peer_key, {})
        was_online = prev.get('online', False)
        old_port = prev.get('tcp_port')
        new_port = data.get('tcp_port')
        self._peers[peer_key] = {**data, 'online': True}
        if not was_online:
            logger.info("peer online: %s @ %s port=%s", uid, ip, new_port)
        elif old_port != new_port:
            logger.info("peer port updated: %s @ %s %s -> %s", uid, ip, old_port, new_port)

    def _mark_offline(self, uid: str, ip: str) -> None:
        peer_key: PeerKey = (uid, ip)
        was_online = self._peers.get(peer_key, {}).get('online', False)
        if peer_key in self._peers:
            self._peers[peer_key]['online'] = False
        if was_online:
            logger.info("peer offline: %s @ %s", uid, ip)
        else:
            logger.debug("peer offline: %s @ %s", uid, ip)

    # ------------------------------------------------------------------
    # NFS queue (fallback)
    # ------------------------------------------------------------------

    def _nfs_drop_path(self, to_uid: str) -> str:
        return os.path.join(self.nfs_dir, 'queue', to_uid, 'drop')

    def _write_nfs_queue(self, envelope: dict) -> None:
        to_uid   = envelope['to']
        send_id  = envelope['send_id']
        drop_dir = self._nfs_drop_path(to_uid)
        path     = os.path.join(drop_dir, f'{send_id}.msg')
        tmp      = os.path.join(drop_dir, f'{send_id}.tmp')
        data     = json.dumps(envelope).encode()
        try:
            os.makedirs(drop_dir, mode=0o733, exist_ok=True)
            with open(tmp, 'wb') as f:
                f.write(data)
            os.replace(tmp, path)
        except Exception as e:
            logger.warning("NFS queue write failed for %s: %s", to_uid, e)

    def _poll_my_nfs_queue(self) -> None:
        """Pick up messages others left in my drop/ while I was offline."""
        drop_dir = self._nfs_drop_path(self.uid)
        if not os.path.exists(drop_dir):
            return
        now = time.time()
        try:
            entries = sorted(
                [e for e in os.scandir(drop_dir) if e.name.endswith('.msg')],
                key=lambda e: e.stat(follow_symlinks=False).st_mtime,
            )
            for entry in entries:
                try:
                    mtime = entry.stat(follow_symlinks=False).st_mtime
                    if now - mtime > QUEUE_TTL:
                        os.unlink(entry.path)
                        continue
                    data = open(entry.path, 'rb').read()
                    os.unlink(entry.path)
                    envelope = json.loads(data)
                    # NFS queue messages may be hours old; skip ts check.
                    # Replay is already prevented by _seen_send_ids + mtime TTL.
                    decrypted = self._decrypt_envelope(envelope, check_ts=False)
                    if decrypted is not None:
                        if (decrypted.get('app_id') == 'skilltalk' and
                                decrypted.get('payload', {}).get('action') == 'command_exec'):
                            self._cmd_queue.enqueue(decrypted)
                        else:
                            self._inbox.enqueue(decrypted)
                except Exception as e:
                    logger.warning("poll_my_nfs_queue entry error: %s", e)
        except Exception as e:
            logger.warning("poll_my_nfs_queue error: %s", e)

    # ------------------------------------------------------------------
    # Envelope encryption / decryption
    # ------------------------------------------------------------------

    def _encrypt_envelope(self, send_id: str, to_uid: str, app_id: str,
                          target_mode: str, desktop_id: Optional[str],
                          msg_type: str, payload: dict,
                          eph_priv: nacl.public.PrivateKey,
                          peer_enc_pub: nacl.public.PublicKey) -> dict:
        ts       = int(time.time())
        nonce    = nacl.utils.random(24)
        box      = nacl.public.Box(eph_priv, peer_enc_pub)
        pt       = json.dumps(payload).encode()
        ct       = box.encrypt(pt, nonce).ciphertext

        nonce_b64 = _b64enc(nonce)
        ct_b64    = _b64enc(ct)
        eph_pub_b64 = _b64enc(bytes(eph_priv.public_key))

        sign_data = (send_id + self.uid + to_uid + str(ts) + nonce_b64 + ct_b64).encode()
        sig = _b64enc(bytes(self._sign_priv.sign(sign_data).signature))

        return {
            'ver':               DAEMON_VERSION,
            'send_id':           send_id,
            'from':              self.uid,
            'from_ip':           self._local_ip,
            'to':                to_uid,
            'app_id':            app_id,
            'target_mode':       target_mode,
            'desktop_id':        desktop_id,
            'msg_type':          msg_type,
            'ts':                ts,
            'sender_eph_pubkey': eph_pub_b64,
            'nonce':             nonce_b64,
            'ciphertext':        ct_b64,
            'from_sig':          sig,
        }

    def _decrypt_envelope(self, envelope: dict, check_ts: bool = True) -> Optional[dict]:
        try:
            from_uid    = envelope['from']
            from_ip     = envelope.get('from_ip', '')
            send_id     = envelope['send_id']
            ts          = envelope['ts']
            nonce_b64   = envelope['nonce']
            ct_b64      = envelope['ciphertext']
            sig_b64     = envelope['from_sig']
            eph_pub_b64 = envelope['sender_eph_pubkey']

            if check_ts and abs(time.time() - ts) > NFS_QUEUE_TS_TOLERANCE:
                logger.warning("envelope ts out of range from %s", from_uid)
                return None

            if send_id in self._seen_send_ids:
                return None
            self._seen_send_ids.add(send_id)

            id_info = self._load_peer_identity(from_uid)
            if id_info is None:
                logger.warning("no identity for %s", from_uid)
                return None

            sign_data = (send_id + from_uid + self.uid + str(ts) + nonce_b64 + ct_b64).encode()
            id_info['sign_pub'].verify(sign_data, _b64dec(sig_b64))

            eph_pub = nacl.public.PublicKey(_b64dec(eph_pub_b64))
            box     = nacl.public.Box(self._enc_priv, eph_pub)
            nonce   = _b64dec(nonce_b64)
            ct      = _b64dec(ct_b64)
            payload = json.loads(box.decrypt(ct, nonce))

            return {
                'send_id':    send_id,
                'from_uid':   from_uid,
                'from_ip':    from_ip,
                'app_id':     envelope['app_id'],
                'target_mode': envelope['target_mode'],
                'desktop_id': envelope.get('desktop_id'),
                'msg_type':   envelope['msg_type'],
                'payload':    payload,
            }
        except Exception as e:
            logger.warning("decrypt_envelope failed: %s", e)
            return None

    # ------------------------------------------------------------------
    # TCP session management
    # ------------------------------------------------------------------

    async def _get_or_connect(self, uid: str, ip: str) -> Optional[tuple]:
        """Return (reader, writer, session_key) for (uid, ip), connecting if needed."""
        peer_key: PeerKey = (uid, ip)
        if peer_key in self._sessions:
            self._session_last_used[peer_key] = time.time()
            return self._sessions[peer_key]

        peer = self._peers.get(peer_key)
        if not peer or not peer.get('online'):
            return None
        tcp_port = peer['tcp_port']

        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(ip, tcp_port), timeout=10)
        except Exception as e:
            logger.warning("TCP connect to %s@%s:%s failed: %s", uid, ip, tcp_port, e)
            return None

        session_key = await self._client_handshake(reader, writer, uid)
        if session_key is None:
            writer.close()
            return None

        self._sessions[peer_key] = (reader, writer, session_key)
        self._session_last_used[peer_key] = time.time()
        asyncio.ensure_future(self._session_reader_loop(peer_key, reader, writer, session_key))
        return self._sessions[peer_key]

    async def _client_handshake(self, reader, writer, peer_uid: str) -> Optional[bytes]:
        """Perform ClientHello/ServerHello handshake. Return session_key."""
        eph_priv = nacl.public.PrivateKey.generate()
        ts       = int(time.time())
        eph_pub_b64 = _b64enc(bytes(eph_priv.public_key))
        sign_data   = f"{self.uid}|{eph_pub_b64}|{ts}".encode()
        sig = _b64enc(bytes(self._sign_priv.sign(sign_data).signature))

        hello = json.dumps({
            'uid':        self.uid,
            'eph_pubkey': eph_pub_b64,
            'ts':         ts,
            'sig':        sig,
        }).encode()
        writer.write(_encode_frame(hello))
        await writer.drain()

        try:
            raw = await asyncio.wait_for(_read_frame(reader), timeout=10)
        except Exception as e:
            logger.warning("handshake read ServerHello failed: %s", e)
            return None

        try:
            srv = json.loads(raw)
            srv_uid    = srv['uid']
            if srv_uid != peer_uid:
                logger.warning("handshake uid mismatch: expected %s got %s", peer_uid, srv_uid)
                return None
            srv_ts = srv['ts']
            if abs(time.time() - srv_ts) > HANDSHAKE_TS_TOLERANCE:
                logger.warning("handshake ts out of range from %s", srv_uid)
                return None

            id_info = self._load_peer_identity(srv_uid)
            if id_info is None:
                logger.warning("no identity for %s during handshake", srv_uid)
                return None
            srv_eph_pub_b64 = srv['eph_pubkey']
            sd = f"{srv_uid}|{srv_eph_pub_b64}|{srv_ts}".encode()
            id_info['sign_pub'].verify(sd, _b64dec(srv['sig']))

            srv_eph_pub = nacl.public.PublicKey(_b64dec(srv_eph_pub_b64))
            shared = nacl.public.Box(eph_priv, srv_eph_pub).shared_key()
            return _derive_session_key(shared, self.uid, srv_uid)
        except Exception as e:
            logger.warning("handshake verification failed: %s", e)
            return None

    async def _server_handshake(self, reader, writer) -> Optional[tuple]:
        """Handle incoming connection. Return (peer_uid, session_key)."""
        try:
            raw = await asyncio.wait_for(_read_frame(reader), timeout=10)
        except Exception as e:
            logger.warning("server handshake read ClientHello failed: %s", e)
            return None

        try:
            cli = json.loads(raw)
            cli_uid    = cli['uid']
            cli_ts     = cli['ts']
            if abs(time.time() - cli_ts) > HANDSHAKE_TS_TOLERANCE:
                logger.warning("handshake ts out of range from %s", cli_uid)
                return None

            id_info = self._load_peer_identity(cli_uid)
            if id_info is None:
                logger.warning("no identity for %s during server handshake", cli_uid)
                return None
            cli_eph_pub_b64 = cli['eph_pubkey']
            sd = f"{cli_uid}|{cli_eph_pub_b64}|{cli_ts}".encode()
            id_info['sign_pub'].verify(sd, _b64dec(cli['sig']))

            eph_priv = nacl.public.PrivateKey.generate()
            ts       = int(time.time())
            eph_pub_b64 = _b64enc(bytes(eph_priv.public_key))
            sign_data   = f"{self.uid}|{eph_pub_b64}|{ts}".encode()
            sig = _b64enc(bytes(self._sign_priv.sign(sign_data).signature))

            hello = json.dumps({
                'uid':        self.uid,
                'eph_pubkey': eph_pub_b64,
                'ts':         ts,
                'sig':        sig,
            }).encode()
            writer.write(_encode_frame(hello))
            await writer.drain()

            cli_eph_pub = nacl.public.PublicKey(_b64dec(cli_eph_pub_b64))
            shared      = nacl.public.Box(eph_priv, cli_eph_pub).shared_key()
            session_key = _derive_session_key(shared, cli_uid, self.uid)
            return cli_uid, session_key
        except Exception as e:
            logger.warning("server handshake failed: %s", e)
            return None

    async def _tcp_send_envelope(self, to_uid: str, to_ip: str, envelope: dict) -> bool:
        sess = await self._get_or_connect(to_uid, to_ip)
        if sess is None:
            return False
        reader, writer, session_key = sess
        try:
            plaintext = json.dumps(envelope).encode()
            payload   = _encrypt(session_key, plaintext)
            writer.write(_encode_frame(payload))
            await writer.drain()
            return True
        except Exception as e:
            logger.warning("TCP send to %s@%s failed: %s", to_uid, to_ip, e)
            self._sessions.pop((to_uid, to_ip), None)
            return False

    async def _session_reader_loop(self, peer_key: PeerKey, reader, writer,
                                   session_key: bytes) -> None:
        """Read encrypted frames from a connected peer."""
        uid, ip = peer_key
        try:
            while True:
                payload = await _read_frame(reader)
                self._session_last_used[peer_key] = time.time()
                try:
                    plaintext = _decrypt(session_key, payload)
                    envelope  = json.loads(plaintext)
                    # tag the source IP for callbacks
                    envelope.setdefault('from_ip', ip)
                    if envelope.get('type') == 'result':
                        self._resolve_pending(
                            envelope['send_id'], envelope['status'], envelope.get('result'))
                    elif envelope.get('type') == 'queue_notify':
                        self._poll_my_nfs_queue()
                    else:
                        self._handle_incoming_envelope(envelope)
                except Exception as e:
                    logger.warning("decrypt/parse frame from %s@%s failed: %s", uid, ip, e)
        except Exception:
            pass
        finally:
            self._sessions.pop(peer_key, None)
            self._session_last_used.pop(peer_key, None)
            try:
                writer.close()
            except Exception:
                pass

    def _handle_incoming_envelope(self, envelope: dict) -> None:
        decrypted = self._decrypt_envelope(envelope)
        if decrypted is None:
            return
        if (decrypted.get('app_id') == 'skilltalk' and
                decrypted.get('payload', {}).get('action') == 'command_exec'):
            self._cmd_queue.enqueue(decrypted)
        else:
            self._inbox.enqueue(decrypted)

    async def _send_queue_notify(self, to_uid: str, to_ip: Optional[str]) -> None:
        """Send a lightweight signal telling the peer to poll its NFS queue now."""
        notify = json.dumps({'type': 'queue_notify'}).encode()
        targets = self._select_peer_targets(to_uid, to_ip, 'ALL')
        for t in targets:
            sess = await self._get_or_connect(to_uid, t['ip'])
            if sess is None:
                continue
            _reader, writer, session_key = sess
            try:
                payload = _encrypt(session_key, notify)
                writer.write(_encode_frame(payload))
                await writer.drain()
            except Exception:
                self._sessions.pop((to_uid, t['ip']), None)

    async def _send_result_to_peer(self, to_uid: str, to_ip: str, send_id: str,
                                   status: str, result: Any) -> None:
        result_env = {
            'ver':     DAEMON_VERSION,
            'type':    'result',
            'send_id': send_id,
            'status':  status,
            'result':  result,
        }
        sess = await self._get_or_connect(to_uid, to_ip)
        if sess is None:
            return
        reader, writer, session_key = sess
        try:
            plaintext = json.dumps(result_env).encode()
            payload   = _encrypt(session_key, plaintext)
            writer.write(_encode_frame(payload))
            await writer.drain()
        except Exception as e:
            logger.warning("send_result_to_peer %s@%s failed: %s", to_uid, to_ip, e)

    async def _handle_incoming_tcp(self, reader, writer) -> None:
        result = await self._server_handshake(reader, writer)
        if result is None:
            writer.close()
            return
        peer_uid, session_key = result
        # derive peer IP from the writer's transport
        try:
            peer_ip = writer.get_extra_info('peername')[0]
        except Exception:
            peer_ip = ''
        peer_key: PeerKey = (peer_uid, peer_ip)
        self._sessions[peer_key] = (reader, writer, session_key)
        self._session_last_used[peer_key] = time.time()
        await self._session_reader_loop(peer_key, reader, writer, session_key)

    # ------------------------------------------------------------------
    # Outgoing send — peer selection by (uid, ip) or target_mode
    # ------------------------------------------------------------------

    def _select_peer_targets(self, to_uid: str,
                             to_ip: Optional[str],
                             target_mode: str) -> List[dict]:
        """Return list of peer dicts to send to."""
        # All online entries for this uid
        candidates = [
            info for (uid, ip), info in self._peers.items()
            if uid == to_uid and info.get('online')
        ]
        if to_ip is not None:
            # pin to specific IP
            return [p for p in candidates if p.get('ip') == to_ip]
        if target_mode == 'ALL':
            return candidates
        # SINGLE or TARGET: pick first / let caller filter by desktop_id later
        return candidates[:1] if candidates else []

    async def _do_send(self, send_id: str, to_uid: str, app_id: str,
                       to_ip: Optional[str],
                       target_mode: str, desktop_id: Optional[str],
                       msg_type: str, payload: dict,
                       wait_for: str, timeout_ms: int,
                       queue_offline: bool = False) -> dict:

        # Self-delivery: bypass TCP/NFS for messages addressed to ourselves.
        # _update_peer ignores our own presence entry, so _select_peer_targets
        # always returns empty for to_uid==self.uid, causing NFS queue fallback.
        if to_uid == self.uid:
            msg = {
                'send_id':    send_id,
                'from_uid':   self.uid,
                'from_ip':    self._local_ip,
                'app_id':     app_id,
                'target_mode': target_mode,
                'desktop_id': desktop_id,
                'msg_type':   msg_type,
                'payload':    payload,
            }
            if (app_id == 'skilltalk' and
                    payload.get('action') == 'command_exec'):
                self._cmd_queue.enqueue(msg)
            else:
                self._inbox.enqueue(msg)
            return {'send_id': send_id, 'status': 'SENT', 'result': None}

        id_info = self._load_peer_identity(to_uid)
        if id_info is None:
            return {'send_id': send_id, 'status': 'ERROR', 'result': 'no identity for recipient'}

        eph_priv = nacl.public.PrivateKey.generate()
        envelope = self._encrypt_envelope(
            send_id, to_uid, app_id, target_mode, desktop_id,
            msg_type, payload, eph_priv, id_info['enc_pub'])

        targets = self._select_peer_targets(to_uid, to_ip, target_mode)
        if not targets:
            # Evict cached presence data for this uid so _poll_presence_for_uid
            # is forced to re-read from disk rather than using mtime cache.
            stale_keys = [k for k in self._mtime_cache if k.startswith(f'{to_uid}@')]
            for k in stale_keys:
                del self._mtime_cache[k]
            for pk in list(self._peers.keys()):
                if pk[0] == to_uid:
                    del self._peers[pk]
            logger.info("send to %s: no targets, evicted cache and re-polling presence", to_uid)
            self._poll_presence_for_uid(to_uid)
            targets = self._select_peer_targets(to_uid, to_ip, target_mode)
        if not targets:
            logger.info("send to %s: still no targets after poll, queue_offline=%s", to_uid, queue_offline)
            if queue_offline:
                self._write_nfs_queue(envelope)
                return {'send_id': send_id, 'status': 'QUEUED', 'result': None}
            return {'send_id': send_id, 'status': 'ERROR', 'result': 'peer offline'}

        pending = PendingSend(send_id, wait_for)
        self._pending[send_id] = pending

        sent_any = False
        for t in targets:
            sent = await self._tcp_send_envelope(to_uid, t['ip'], envelope)
            if sent:
                sent_any = True

        if not sent_any:
            # All TCP targets failed — cached peer info may be stale (e.g. peer
            # restarted with a new port).  Evict stale entries, re-poll presence,
            # and make one more attempt before falling back to NFS queue.
            logger.info("send to %s: all TCP targets failed, evicting and re-polling", to_uid)
            for t in targets:
                self._peers.pop((to_uid, t['ip']), None)
                self._mtime_cache.pop(self._presence_filename(to_uid, t['ip']), None)
            stale_keys = [k for k in self._mtime_cache if k.startswith(f'{to_uid}@')]
            for k in stale_keys:
                del self._mtime_cache[k]
            self._poll_presence_for_uid(to_uid)
            retry_targets = self._select_peer_targets(to_uid, to_ip, target_mode)
            logger.info("send to %s: retry targets after re-poll: %s", to_uid,
                        [(t['ip'], t.get('tcp_port')) for t in retry_targets])
            for t in retry_targets:
                sent = await self._tcp_send_envelope(to_uid, t['ip'], envelope)
                if sent:
                    sent_any = True
                    break

        if not sent_any:
            self._pending.pop(send_id, None)
            if queue_offline:
                self._write_nfs_queue(envelope)
                await self._send_queue_notify(to_uid, to_ip)
                return {'send_id': send_id, 'status': 'QUEUED', 'result': None}
            return {'send_id': send_id, 'status': 'ERROR', 'result': 'peer offline'}

        # TCP succeeded — also write NFS queue as backup when queue_offline is set.
        # The receiver deduplicates by send_id, so double-delivery is harmless.
        # This ensures delivery even if the TCP frame was accepted by the kernel
        # but dropped before the peer processed it (e.g. handshake race on restart).
        if queue_offline:
            self._write_nfs_queue(envelope)
            await self._send_queue_notify(to_uid, to_ip)

        if wait_for == 'sent':
            self._pending.pop(send_id, None)
            return {'send_id': send_id, 'status': 'SENT', 'result': None}

        try:
            timeout_s = timeout_ms / 1000.0
            result = await asyncio.wait_for(pending.future, timeout=timeout_s)
            return result
        except asyncio.TimeoutError:
            self._pending.pop(send_id, None)
            return {'send_id': send_id, 'status': 'ERROR', 'result': 'timeout'}

    def _resolve_pending(self, send_id: str, status: str, result: Any) -> None:
        pending = self._pending.pop(send_id, None)
        if pending and not pending.future.done():
            pending.future.set_result({'send_id': send_id, 'status': status, 'result': result})

    # ------------------------------------------------------------------
    # Desktop delivery
    # ------------------------------------------------------------------

    async def _cmd_exec_loop(self) -> None:
        """Dedicated loop for command_exec — never blocked by desktop delivery parking."""
        import threading as _threading
        while True:
            await self._cmd_queue.wait()
            msg = self._cmd_queue.dequeue()
            if msg is None:
                continue
            _threading.Thread(
                target=self._handle_skilltalk_command_exec,
                args=(msg,),
                daemon=True,
            ).start()

    async def _delivery_loop(self) -> None:
        while True:
            await self._inbox.wait()
            msg = self._inbox.dequeue()
            if msg is None:
                continue
            app_id = msg.get('app_id')
            has_candidate = any(
                info['app_id'] == app_id for info in self._desktops.values()
            )
            if not has_candidate:
                self._inbox.enqueue(msg)
                self._desktop_registered.clear()
                try:
                    await asyncio.wait_for(
                        asyncio.shield(self._desktop_registered.wait()),
                        timeout=DELIVERY_PARK_TIMEOUT,
                    )
                except asyncio.TimeoutError:
                    pass
                continue
            await self._deliver_to_desktops(msg)

    async def _deliver_to_desktops(self, msg: dict) -> None:
        import urllib.request
        import urllib.error

        app_id      = msg.get('app_id')
        target_mode = msg.get('target_mode', 'SINGLE')
        target_did  = msg.get('desktop_id')

        candidates = [
            (did, info) for did, info in self._desktops.items()
            if info['app_id'] == app_id
        ]
        if not candidates:
            self._inbox.enqueue(msg)
            await asyncio.sleep(1)
            return

        if target_mode == 'TARGET' and target_did:
            targets = [(did, info) for did, info in candidates if did == target_did]
        elif target_mode == 'SINGLE':
            targets = [candidates[0]]
        else:  # ALL
            targets = candidates

        body = json.dumps({
            'send_id':  msg['send_id'],
            'from_uid': msg['from_uid'],
            'from_ip':  msg.get('from_ip', ''),
            'app_id':   app_id,
            'msg_type': msg['msg_type'],
            'payload':  msg['payload'],
        }).encode()

        def _http_post(port: int, data: bytes) -> bool:
            req = urllib.request.Request(
                f'http://127.0.0.1:{port}/message',
                data=data,
                headers={'Content-Type': 'application/json'},
                method='POST',
            )
            with urllib.request.urlopen(req, timeout=DELIVERY_CB_TIMEOUT) as resp:
                resp.read()
            return True

        loop = asyncio.get_event_loop()
        delivered = False
        failed_dids = []
        for did, info in targets:
            port = info['callback_port']
            try:
                await loop.run_in_executor(None, _http_post, port, body)
                delivered = True
            except Exception as e:
                logger.warning("deliver to desktop %s port %s failed: %s", did, port, e)
                failed_dids.append(did)

        # remove desktops that could not be reached
        for did in failed_dids:
            self._desktops.pop(did, None)

        if delivered:
            from_uid = msg['from_uid']
            from_ip  = msg.get('from_ip', '')
            action   = msg.get('payload', {}).get('action', '')
            logger.info("delivered to desktop: app=%s action=%s", app_id, action)
            self._resolve_pending(msg['send_id'], 'DELIVERED', None)
            asyncio.ensure_future(
                self._send_result_to_peer(from_uid, from_ip, msg['send_id'], 'DELIVERED', None))
        else:
            # all candidates failed — re-enqueue for when a new desktop registers
            self._inbox.enqueue(msg)

    # ------------------------------------------------------------------
    # REST API (Unix domain socket)
    # ------------------------------------------------------------------

    def _make_rest_handler(self):
        daemon = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):
                pass  # suppress default access log

            def _send_json(self, code: int, obj: Any) -> None:
                body = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _read_body(self) -> dict:
                length = int(self.headers.get('Content-Length', 0))
                return json.loads(self.rfile.read(length)) if length else {}

            def do_GET(self):
                parsed = urlparse(self.path)
                if parsed.path == '/peers':
                    daemon._poll_presence()
                    result = [
                        {
                            'uid':      info.get('uid', uid),
                            'ip':       ip,
                            'tcp_port': info.get('tcp_port', 0),
                            'online':   info.get('online', False),
                            'ts':       info.get('ts', 0),
                        }
                        for (uid, ip), info in daemon._peers.items()
                    ]
                    self._send_json(200, result)
                elif parsed.path == '/presence':
                    from urllib.parse import parse_qs
                    qs = parse_qs(parsed.query)
                    peers_param = qs.get('peers', [''])[0]
                    if not peers_param:
                        self._send_json(400, {'error': 'peers parameter required'})
                        return
                    result = []
                    for token in peers_param.split(','):
                        token = token.strip()
                        if '@' not in token:
                            continue
                        uid, ip = token.rsplit('@', 1)
                        info = daemon._poll_presence_one(uid, ip)
                        result.append({
                            'uid':      uid,
                            'ip':       ip,
                            'tcp_port': info.get('tcp_port', 0),
                            'online':   info.get('online', False),
                            'ts':       info.get('ts', 0),
                        })
                    self._send_json(200, result)
                elif parsed.path == '/status':
                    self._send_json(200, {
                        'version':       DAEMON_VERSION,
                        'uptime':        int(time.time() - daemon._start_time),
                        'peer_count':    len(daemon._peers),
                        'desktop_count': len(daemon._desktops),
                    })
                else:
                    self._send_json(404, {'error': 'not found'})

            def do_POST(self):
                parsed = urlparse(self.path)
                body   = self._read_body()

                if parsed.path == '/send':
                    future = asyncio.run_coroutine_threadsafe(
                        daemon._do_send(
                            send_id    = body.get('send_id', str(uuid.uuid4())),
                            to_uid     = body['to_uid'],
                            app_id     = body['app_id'],
                            to_ip      = body.get('to_ip'),
                            target_mode = body.get('target_mode', 'SINGLE'),
                            desktop_id  = body.get('desktop_id'),
                            msg_type    = body.get('msg_type', 'postmessage'),
                            payload     = body.get('payload', {}),
                            wait_for      = body.get('wait_for', 'delivered'),
                            timeout_ms    = body.get('timeout_ms', 5000),
                            queue_offline = body.get('queue_offline', False),
                        ),
                        daemon._loop,
                    )
                    try:
                        result = future.result(timeout=body.get('timeout_ms', 5000) / 1000 + 2)
                        self._send_json(200, result)
                    except Exception as e:
                        self._send_json(500, {'error': str(e)})

                elif parsed.path == '/desktops/register':
                    desktop_id    = body['desktop_id']
                    app_id        = body['app_id']
                    callback_port = body['callback_port']
                    daemon._desktops[desktop_id] = {
                        'app_id':        app_id,
                        'callback_port': callback_port,
                    }
                    logger.info("desktop registered: %s app=%s port=%s",
                                desktop_id, app_id, callback_port)
                    if daemon._desktop_registered is not None:
                        daemon._loop.call_soon_threadsafe(daemon._desktop_registered.set)
                    self._send_json(200, {'ok': True})

                else:
                    self._send_json(404, {'error': 'not found'})

            def do_DELETE(self):
                parts = self.path.strip('/').split('/')
                if len(parts) == 2 and parts[0] == 'desktops':
                    desktop_id = parts[1]
                    daemon._desktops.pop(desktop_id, None)
                    logger.info("desktop unregistered: %s", desktop_id)
                    self._send_json(200, {'ok': True})
                else:
                    self._send_json(404, {'error': 'not found'})

        return Handler

    # ------------------------------------------------------------------
    # Build update polling (5b)
    # ------------------------------------------------------------------

    def _check_build_update(self) -> None:
        """Poll buildinfo.ini; execv-restart if build number changed."""
        try:
            if not os.path.exists(self._buildinfo_path):
                return
            mtime = os.stat(self._buildinfo_path).st_mtime
            if mtime == self._buildinfo_mtime:
                return
            self._buildinfo_mtime = mtime

            cp = configparser.ConfigParser()
            cp.read(self._buildinfo_path)
            build_str = cp.get('buildinfo', 'build', fallback=None)
            if build_str is None:
                return
            build = int(build_str)

            if self._last_build is None:
                self._last_build = build
                return

            if build != self._last_build:
                logger.info("build changed %d -> %d, restarting", self._last_build, build)
                asyncio.ensure_future(self._graceful_restart())
        except Exception as e:
            logger.warning("build update check failed: %s", e)

    async def _graceful_restart(self) -> None:
        await self._notify_desktops_restarting()
        # wait for pending to drain (up to 10s)
        deadline = time.time() + 10
        while self._pending and time.time() < deadline:
            await asyncio.sleep(0.2)
        for _key, (reader, writer, _sk) in list(self._sessions.items()):
            try:
                writer.close()
            except Exception:
                pass
        # remove sock file so wrapper can detect restart and re-register
        try:
            os.unlink(self._sock_path)
        except OSError:
            pass
        # keep presence file (will be re-published after execv)
        logger.info("restarting via execv: %s %s", sys.executable, sys.argv)
        os.execv(sys.executable, [sys.executable] + sys.argv)

    async def _notify_desktops_restarting(self) -> None:
        import urllib.request
        import urllib.error
        body = json.dumps({'event': 'daemon_restarting'}).encode()
        loop = asyncio.get_event_loop()
        for did, info in self._desktops.items():
            port = info['callback_port']
            try:
                def _post(p=port, b=body):
                    req = urllib.request.Request(
                        f'http://127.0.0.1:{p}/message',
                        data=b,
                        headers={'Content-Type': 'application/json'},
                        method='POST',
                    )
                    with urllib.request.urlopen(req, timeout=3) as resp:
                        resp.read()
                await loop.run_in_executor(None, _post)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Skilltalk command execution (peerbus-native, no desktop required)
    # ------------------------------------------------------------------

    def _get_skilltalk_admins(self) -> list:
        from lib.config import _get_default_config_path
        default_path = _get_default_config_path()
        if not default_path or not os.path.exists(default_path):
            return []
        cp = configparser.ConfigParser()
        cp.read(default_path)
        raw = cp.get('skilltalk', 'admins', fallback='')
        return [u.strip() for u in raw.split(',') if u.strip()]

    def _handle_skilltalk_command_exec(self, msg: dict) -> None:
        import subprocess
        payload   = msg.get('payload', {})
        from_uid  = msg.get('from_uid', '')
        from_ip   = msg.get('from_ip', '')

        admins = self._get_skilltalk_admins()
        if from_uid not in admins:
            logger.warning("command_exec rejected: from_uid=%r not in admins=%r", from_uid, admins)
            return

        cmd         = payload.get('cmd', '')
        room_id     = payload.get('chatroom_id')
        timeout     = int(payload.get('timeout') or 30)
        cmd_chat_id = payload.get('cmd_chat_id')

        if not cmd or not room_id:
            logger.warning("command_exec: missing cmd or chatroom_id")
            return

        received_at = int(time.time())
        try:
            import tempfile as _tempfile
            # Write stdout/stderr to temp files instead of PIPE so that
            # background processes spawned by the command (e.g. "sleep 30 &")
            # do not keep the pipe fds open and block proc.wait().
            with _tempfile.TemporaryFile() as out_f, \
                 _tempfile.TemporaryFile() as err_f:
                proc = subprocess.Popen(
                    cmd, shell=True, stdout=out_f, stderr=err_f,
                )
                try:
                    proc.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                    raise
                out_f.seek(0); err_f.seek(0)
                raw_out = out_f.read()
                raw_err = err_f.read()
            stdout   = raw_out.decode('utf-8', errors='replace')
            stderr   = raw_err.decode('utf-8', errors='replace')
            exitcode = proc.returncode
        except subprocess.TimeoutExpired:
            stdout   = ''
            stderr   = f'[timeout after {timeout}s]'
            exitcode = -1
        except Exception as e:
            stdout   = ''
            stderr   = str(e)
            exitcode = -1

        finished_at = int(time.time())
        result_payload = {
            'action':       'command_result',
            'chatroom_id':  room_id,
            'executor_uid': self.uid,
            'exitcode':     exitcode,
            'stdout':       stdout,
            'stderr':       stderr,
            'received_at':  received_at,
            'finished_at':  finished_at,
            'cmd_chat_id':  cmd_chat_id,
            'hostname':     socket.gethostname(),
            'ip':           self._local_ip,
        }
        send_id = str(uuid.uuid4())
        logger.info("command_exec done: uid=%s room=%s exit=%d, sending result to %s",
                    self.uid, room_id, exitcode, from_uid)
        asyncio.run_coroutine_threadsafe(
            self._do_send_command_result(send_id, from_uid, result_payload),
            self._loop,
        )

    async def _do_send_command_result(self, send_id: str, to_uid: str, payload: dict) -> None:
        """Send command_result: attempt TCP and always write NFS queue as backup."""
        # Self-delivery: bypass encryption/NFS, enqueue directly.
        if to_uid == self.uid:
            msg = {
                'send_id':    send_id,
                'from_uid':   self.uid,
                'from_ip':    self._local_ip,
                'app_id':     'skilltalk',
                'target_mode': 'ALL',
                'desktop_id': None,
                'msg_type':   'postmessage',
                'payload':    payload,
            }
            self._inbox.enqueue(msg)
            return

        id_info = self._load_peer_identity(to_uid)
        if id_info is None:
            logger.warning("command_result: no identity for %s, dropping", to_uid)
            return

        eph_priv = nacl.public.PrivateKey.generate()
        envelope = self._encrypt_envelope(
            send_id, to_uid, 'skilltalk', 'ALL', None,
            'postmessage', payload, eph_priv, id_info['enc_pub'])

        # Always persist to NFS queue first — guarantees delivery even if TCP succeeds
        # but admin peerbus is torn down before it can hand off to desktop.
        # Dedup via send_id prevents double-processing on the receiving side.
        self._write_nfs_queue(envelope)

        # Also try TCP for low-latency delivery
        targets = self._select_peer_targets(to_uid, None, 'ALL')
        if not targets:
            self._poll_presence_for_uid(to_uid)
            targets = self._select_peer_targets(to_uid, None, 'ALL')
        for t in targets:
            await self._tcp_send_envelope(to_uid, t['ip'], envelope)

    # ------------------------------------------------------------------
    # Idle TCP session cleanup
    # ------------------------------------------------------------------

    async def _idle_session_cleanup(self) -> None:
        now = time.time()
        for peer_key in list(self._sessions.keys()):
            last = self._session_last_used.get(peer_key, 0)
            if now - last > IDLE_TCP_TIMEOUT:
                _reader, writer, _sk = self._sessions.pop(peer_key)
                self._session_last_used.pop(peer_key, None)
                try:
                    writer.close()
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Main async run loop
    # ------------------------------------------------------------------

    async def _run(self) -> None:
        import threading

        self._desktop_registered = asyncio.Event()
        self._desktop_registered.set()  # allow first delivery attempt immediately

        # TCP server — dynamic port
        tcp_server = await asyncio.start_server(
            self._handle_incoming_tcp,
            host='0.0.0.0',
            port=0,
        )
        self._tcp_port = tcp_server.sockets[0].getsockname()[1]

        # Presence uses tcp_port so publish after we know the port
        self._publish_presence()
        self._poll_my_nfs_queue()

        # Remove stale sock file from previous run if process is gone
        if os.path.exists(self._sock_path):
            try:
                os.unlink(self._sock_path)
            except OSError:
                pass

        # Unix domain socket REST server in a daemon thread
        handler_class = self._make_rest_handler()
        rest_server   = _UnixSocketHTTPServer(self._sock_path, handler_class)
        rest_thread   = threading.Thread(target=rest_server.serve_forever, daemon=True)
        rest_thread.start()
        logger.info("peerbus daemon started uid=%s tcp_port=%d sock=%s",
                    self.uid, self._tcp_port, self._sock_path)

        asyncio.ensure_future(self._cmd_exec_loop())
        asyncio.ensure_future(self._delivery_loop())

        tick = 0
        async with tcp_server:
            while True:
                await asyncio.sleep(1)
                tick += 1

                if tick % PRESENCE_HEARTBEAT_INTERVAL == 0:
                    self._publish_presence()

                if tick % NFS_QUEUE_POLL_INTERVAL == 0:
                    self._poll_my_nfs_queue()

                if tick % IDLE_TCP_TIMEOUT == 0:
                    await self._idle_session_cleanup()

                if tick % BUILD_POLL_INTERVAL == 0:
                    self._check_build_update()


# ---------------------------------------------------------------------------
# Singleton check helpers (called from wrapper / main)
# ---------------------------------------------------------------------------

def _get_pid_path() -> str:
    from lib.config import get_config_home
    return os.path.join(get_config_home(), 'peerbus', 'daemon.pid')


def _get_sock_path() -> str:
    from lib.config import get_config_home
    return os.path.join(get_config_home(), 'peerbus', 'daemon.sock')


def is_daemon_running() -> bool:
    pid_path = _get_pid_path()
    if not os.path.exists(pid_path):
        return False
    try:
        pid = int(open(pid_path).read().strip())
        os.kill(pid, 0)
        return True
    except (ValueError, OSError):
        return False


def _get_nfs_dir(skillup_root: str) -> str:
    """Resolve $PEERBUS_NFS_DIR with config priority."""
    from lib.config import _get_default_config_path, _expand_config_value
    import configparser

    default_path = _get_default_config_path()
    if default_path and os.path.exists(default_path):
        ini_dir = os.path.dirname(os.path.abspath(default_path))
        cp = configparser.ConfigParser()
        cp.read(default_path)
        raw = cp.get('desktop', 'general.peer_bus_nfs_dir', fallback=None)
        if raw:
            return _expand_config_value(raw, ini_dir)

    return os.path.join(skillup_root, 'desktop', 'peerbus', 'data')


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _main():
    import argparse
    parser = argparse.ArgumentParser(description='peerbus daemon')
    parser.add_argument('--uid',     required=True)
    parser.add_argument('--nfs-dir', required=False, default=None)
    args = parser.parse_args()

    skillup_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    nfs_dir = args.nfs_dir or _get_nfs_dir(skillup_root)

    daemon = PeerbusDaemon(uid=args.uid, nfs_dir=nfs_dir, skillup_root=skillup_root)

    def _sig_handler(sig, frame):
        daemon.stop()

    signal.signal(signal.SIGTERM, _sig_handler)
    signal.signal(signal.SIGINT,  _sig_handler)

    daemon.start()


if __name__ == '__main__':
    # Ensure skillup root (parent of peerbus/) is on sys.path so `lib` is importable
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _root not in sys.path:
        sys.path.insert(0, _root)
    _main()
