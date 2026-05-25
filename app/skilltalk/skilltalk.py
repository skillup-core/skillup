"""
Skilltalk — multi-user chat app built on peerbus.
"""

import base64
import getpass
import os
import socket
import sys
import threading
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from lib.baseapp import BaseApp
from lib.appmgr import register_app_class

_APP_DIR = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_DB_PATH = os.path.join(_APP_DIR, 'data', 'skilltalk.db')

APP_ID = 'skilltalk'


def _my_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('10.255.255.255', 1))
        return s.getsockname()[0]
    except Exception:
        return '127.0.0.1'
    finally:
        try:
            s.close()
        except Exception:
            pass


class SkilltalkApp(BaseApp):

    def __init__(self, engine, context):
        super().__init__(engine, context)
        self._db = None
        self._wrapper = None
        self._desktop_id = str(uuid.uuid4())
        self._uid = getpass.getuser()
        self._my_ip = _my_ip()
        self._active_room_id = None
        self._cleanup_thread = None
        self._stop_cleanup = threading.Event()
        self._account_db_path = ''

    # ------------------------------------------------------------------
    # BaseApp required
    # ------------------------------------------------------------------

    def on_run_cli(self, args):
        print("skilltalk: desktop mode only", file=sys.stderr)
        return 1

    def on_run_desktop_initialize(self):
        self._init_db()
        self._init_account_db()
        try:
            self._init_peerbus()
        except Exception as e:
            print(f"[warn ] skilltalk peerbus init failed (offline mode): {e}", file=sys.stderr)
        self._start_cleanup_scheduler()

        self.register_handlers({
            'st_init':             self._h_init,
            'st_get_rooms':        self._h_get_rooms,
            'st_create_room':      self._h_create_room,
            'st_get_chats':        self._h_get_chats,
            'st_send':             self._h_send,
            'st_send_image':       self._h_send_image,
            'st_delete_chat':      self._h_delete_chat,
            'st_leave_room':       self._h_leave_room,
            'st_mark_focus':       self._h_mark_focus,
            'st_get_user_avatar':  self._h_get_user_avatar,
            'st_search_users':     self._h_search_users,
        })
        return 0

    def on_close(self):
        self._stop_cleanup.set()
        if self._wrapper:
            try:
                self._wrapper.unregister(self._desktop_id)
            except Exception:
                pass
        if self._db:
            self._db.close()

    # ------------------------------------------------------------------
    # DB init
    # ------------------------------------------------------------------

    def _resolve_db_path(self) -> str:
        from lib.config import _get_default_config_path, _expand_config_value
        import configparser

        default_path = _get_default_config_path()
        if default_path and os.path.exists(default_path):
            ini_dir = os.path.dirname(os.path.abspath(default_path))
            cp = configparser.ConfigParser()
            cp.read(default_path)
            raw = cp.get('skilltalk', 'db_path', fallback=None)
            if raw:
                return _expand_config_value(raw, ini_dir)

        return _DEFAULT_DB_PATH

    def _get_retention(self) -> tuple:
        import configparser
        from lib.config import _get_default_config_path

        chatroom_days = 30
        chat_days = 30
        default_path = _get_default_config_path()
        if default_path and os.path.exists(default_path):
            cp = configparser.ConfigParser()
            cp.read(default_path)
            try:
                chatroom_days = int(cp.get('skilltalk', 'chatroom_retention_days', fallback='30'))
            except Exception:
                pass
            try:
                chat_days = int(cp.get('skilltalk', 'chat_retention_days', fallback='30'))
            except Exception:
                pass
        return chatroom_days, chat_days

    def _init_db(self):
        from app.skilltalk.db import init_db, SkilltalkDB
        db_path = self._resolve_db_path()
        init_db(db_path)
        self._db = SkilltalkDB(db_path)

    def _init_account_db(self):
        try:
            from desktop import account as account_mod
            from lib.config import get_desktop_config
            cfg = get_desktop_config('general.account_db', '').strip()
            self._account_db_path = cfg if cfg else account_mod.get_default_account_db_path()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Peerbus init
    # ------------------------------------------------------------------

    def _init_peerbus(self):
        from lib.peerbuswrapper import PeerbusWrapper

        self._wrapper = PeerbusWrapper()
        self._wrapper.on_message(self._on_peerbus_message)
        self._wrapper.register(self._desktop_id, app_id=APP_ID, callback_port=0)
        self._wrapper.ensure_registered()

    # ------------------------------------------------------------------
    # Peerbus message handler
    # ------------------------------------------------------------------

    def _on_peerbus_message(self, send_id, from_uid, from_ip, app_id, msg_type, payload):
        if not payload or app_id != APP_ID:
            return
        action = payload.get('action')
        if action == 'new_chat':
            self._handle_new_chat(payload)
        elif action == 'chat_deleted':
            self._handle_chat_deleted(payload)
        elif action == 'member_left':
            self._handle_member_left(payload)
        elif action == 'room_created':
            self._handle_room_created(payload)
        elif action == 'room_deleted':
            self._handle_room_deleted(payload)

    def _broadcast(self, action: str, data: dict):
        import json as _json
        msg = _json.dumps({
            'jsonrpc': '2.0',
            'method': 'callJS',
            'params': {
                'function_name': action,
                'json_args': _json.dumps(data),
                'broadcast': True,
            },
        })
        print(msg, flush=True)

    def _handle_new_chat(self, payload):
        room_id = payload.get('chatroom_id')
        chat_id = payload.get('chat_id')
        self._broadcast('onChatNew', {'chatroom_id': room_id, 'chat_id': chat_id})

    def _handle_chat_deleted(self, payload):
        room_id = payload.get('chatroom_id')
        chat_id = payload.get('chat_id')
        self._broadcast('onChatDeleted', {'chatroom_id': room_id, 'chat_id': chat_id})

    def _handle_member_left(self, payload):
        room_id = payload.get('chatroom_id')
        uid = payload.get('uid')
        self._broadcast('onMemberLeft', {'chatroom_id': room_id, 'uid': uid})

    def _handle_room_created(self, payload):
        room_id = payload.get('chatroom_id')
        created_by = payload.get('created_by')
        self._broadcast('onRoomCreated', {'chatroom_id': room_id, 'created_by': created_by})

    def _handle_room_deleted(self, payload):
        room_id = payload.get('chatroom_id')
        self._broadcast('onRoomDeleted', {'chatroom_id': room_id})

    # ------------------------------------------------------------------
    # Cleanup scheduler
    # ------------------------------------------------------------------

    def _start_cleanup_scheduler(self):
        def run():
            self._run_cleanup()
            while not self._stop_cleanup.wait(3600):
                self._run_cleanup()

        self._cleanup_thread = threading.Thread(target=run, daemon=True)
        self._cleanup_thread.start()

    def _run_cleanup(self):
        try:
            chatroom_days, chat_days = self._get_retention()
            self._db.cleanup(chatroom_days, chat_days)
        except Exception as e:
            print(f"[warn ] skilltalk cleanup error: {e}", file=sys.stderr)

    # ------------------------------------------------------------------
    # Peerbus post helper
    # ------------------------------------------------------------------

    def _post_to_room_members(self, room_id: int, payload: dict):
        if not self._wrapper:
            return
        members = self._db.get_room_members(room_id)
        for uid in members:
            try:
                self._wrapper.post(
                    to_uid=uid,
                    app_id=APP_ID,
                    payload=payload,
                    target_mode='ALL',
                    wait_for='sent',
                    timeout_ms=3000,
                    queue_offline=True,
                )
            except Exception as e:
                print(f"[warn ] peerbus post to {uid} failed: {e}", file=sys.stderr)

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _h_init(self, data, language):
        rooms = self._db.get_rooms_for_uid(self._uid)
        for r in rooms:
            r['is_admin'] = (r.get('created_by') == self._uid)
        return {
            'success': True,
            'uid': self._uid,
            'ip': self._my_ip,
            'rooms': rooms,
        }

    def _h_get_rooms(self, data, language):
        rooms = self._db.get_rooms_for_uid(self._uid)
        for r in rooms:
            r['is_admin'] = (r.get('created_by') == self._uid)
        return {'success': True, 'rooms': rooms}

    def _h_create_room(self, data, language):
        name = (data.get('name') or '').strip()
        member_uids = data.get('member_uids') or []
        if not name:
            return {'success': False, 'error': 'name required'}
        if self._uid not in member_uids:
            member_uids = [self._uid] + list(member_uids)

        room_id = self._db.create_room(name, member_uids, created_by=self._uid)
        payload = {'action': 'room_created', 'chatroom_id': room_id, 'created_by': self._uid}
        threading.Thread(target=self._post_to_room_members, args=(room_id, payload), daemon=True).start()
        return {'success': True, 'chatroom_id': room_id}

    def _h_get_chats(self, data, language):
        room_id = data.get('chatroom_id')
        before_id = data.get('before_id')
        limit = min(int(data.get('limit', 50)), 200)
        if not room_id:
            return {'success': False, 'error': 'chatroom_id required'}
        if not self._db.is_member(room_id, self._uid):
            return {'success': False, 'error': 'not a member'}
        chats = self._db.get_chats(room_id, before_id=before_id, limit=limit)
        return {'success': True, 'chats': chats}

    def _h_send(self, data, language):
        room_id = data.get('chatroom_id')
        text = (data.get('text') or '').strip()
        if not room_id or not text:
            return {'success': False, 'error': 'chatroom_id and text required'}
        if not self._db.is_member(room_id, self._uid):
            return {'success': False, 'error': 'not a member'}

        chat_id = self._db.insert_chat(room_id, self._uid, self._my_ip, text, 'text/plain')
        preview = text[:60] + ('...' if len(text) > 60 else '')
        payload = {
            'action': 'new_chat',
            'chatroom_id': room_id,
            'chat_id': chat_id,
            'sender_uid': self._uid,
            'preview': preview,
        }
        threading.Thread(target=self._post_to_room_members, args=(room_id, payload), daemon=True).start()

        chat = self._db.get_chat_by_id(chat_id)
        return {'success': True, 'chat': chat}

    _ALLOWED_IMAGE_MIMETYPES = {'image/png', 'image/jpeg', 'image/gif', 'image/webp'}
    _MAX_IMAGE_B64_BYTES = 1024 * 1024  # 1MB

    def _h_send_image(self, data, language):
        room_id = data.get('chatroom_id')
        mimetype = (data.get('mimetype') or '').strip().lower()
        data_b64 = (data.get('data_base64') or '').strip()

        if not room_id or not mimetype or not data_b64:
            return {'success': False, 'error': 'chatroom_id, mimetype and data_base64 required'}
        if mimetype not in self._ALLOWED_IMAGE_MIMETYPES:
            return {'success': False, 'error': f'unsupported image type: {mimetype}'}
        if len(data_b64) > self._MAX_IMAGE_B64_BYTES:
            return {'success': False, 'error': 'image_too_large'}
        if not self._db.is_member(room_id, self._uid):
            return {'success': False, 'error': 'not a member'}

        try:
            base64.b64decode(data_b64, validate=True)
        except Exception:
            return {'success': False, 'error': 'invalid base64 data'}

        chat_id = self._db.insert_chat(room_id, self._uid, self._my_ip, data_b64, mimetype)
        payload = {
            'action': 'new_chat',
            'chatroom_id': room_id,
            'chat_id': chat_id,
            'sender_uid': self._uid,
            'preview': '[image]',
        }
        threading.Thread(target=self._post_to_room_members, args=(room_id, payload), daemon=True).start()

        chat = self._db.get_chat_by_id(chat_id)
        return {'success': True, 'chat': chat}

    def _h_delete_chat(self, data, language):
        chat_id = data.get('chat_id')
        if not chat_id:
            return {'success': False, 'error': 'chat_id required'}

        chat = self._db.get_chat_by_id(chat_id)
        if not chat:
            return {'success': False, 'error': 'not found'}
        room_id = chat['chatroom_id']

        ok = self._db.delete_chat(chat_id, self._uid)
        if not ok:
            return {'success': False, 'error': 'delete failed (not owner or not found)'}

        payload = {'action': 'chat_deleted', 'chatroom_id': room_id, 'chat_id': chat_id}
        threading.Thread(target=self._post_to_room_members, args=(room_id, payload), daemon=True).start()
        return {'success': True}

    def _h_leave_room(self, data, language):
        room_id = data.get('chatroom_id')
        if not room_id:
            return {'success': False, 'error': 'chatroom_id required'}
        if not self._db.is_member(room_id, self._uid):
            return {'success': False, 'error': 'not a member'}

        room = self._db.get_room(room_id)
        is_admin = room and room.get('created_by') == self._uid

        members_before = self._db.get_room_members(room_id)
        others = [uid for uid in members_before if uid != self._uid]

        if is_admin:
            # Admin deletes the entire room
            self._db.delete_room(room_id)
            payload = {'action': 'room_deleted', 'chatroom_id': room_id}

            def _notify_deleted(uids, p):
                for uid in uids:
                    try:
                        self._wrapper.post(
                            to_uid=uid,
                            app_id=APP_ID,
                            payload=p,
                            target_mode='ALL',
                            wait_for='sent',
                            timeout_ms=3000,
                            queue_offline=True,
                        )
                    except Exception as e:
                        print(f"[warn ] peerbus post to {uid} failed: {e}", file=sys.stderr)

            threading.Thread(target=_notify_deleted, args=(others, payload), daemon=True).start()
            return {'success': True, 'deleted': True}

        # Regular member leaves
        remaining = self._db.leave_room(room_id, self._uid)

        if remaining > 0:
            payload = {'action': 'member_left', 'chatroom_id': room_id, 'uid': self._uid}

            def _notify_leave(uids, p):
                for uid in uids:
                    try:
                        self._wrapper.post(
                            to_uid=uid,
                            app_id=APP_ID,
                            payload=p,
                            target_mode='ALL',
                            wait_for='sent',
                            timeout_ms=3000,
                            queue_offline=True,
                        )
                    except Exception as e:
                        print(f"[warn ] peerbus post to {uid} failed: {e}", file=sys.stderr)

            threading.Thread(target=_notify_leave, args=(others, payload), daemon=True).start()

        return {'success': True, 'remaining_members': remaining}

    def _h_mark_focus(self, data, language):
        self._active_room_id = data.get('chatroom_id')
        return {'success': True}

    def _h_search_users(self, data, language):
        query = (data.get('query') or '').strip()
        if not query or not self._account_db_path:
            return {'success': True, 'users': []}
        try:
            from desktop.account import _get_connection
            conn = _get_connection(self._account_db_path)
            try:
                like = '%' + query + '%'
                rows = conn.execute(
                    "SELECT id, name FROM accounts WHERE activated=1 "
                    "AND (id LIKE ? OR name LIKE ?) ORDER BY id LIMIT 20",
                    (like, like)
                ).fetchall()
                return {'success': True, 'users': [{'id': r['id'], 'name': r['name']} for r in rows]}
            finally:
                conn.close()
        except Exception:
            return {'success': True, 'users': []}

    def _h_get_user_avatar(self, data, language):
        uid = (data.get('uid') or '').strip()
        if not uid or not self._account_db_path:
            return {'success': True, 'avatar': None, 'mime': None}
        try:
            from desktop import account as account_mod
            photo_bytes, mime = account_mod.get_account_photo(self._account_db_path, uid, 'small')
            if photo_bytes:
                return {
                    'success': True,
                    'avatar': base64.b64encode(photo_bytes).decode('ascii'),
                    'mime': mime or 'image/jpeg',
                }
        except Exception:
            pass
        return {'success': True, 'avatar': None, 'mime': None}


register_app_class(SkilltalkApp)
