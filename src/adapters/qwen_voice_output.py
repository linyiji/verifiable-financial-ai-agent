"""Explicit Beijing Kiki -> existing PCM contract; one reader per Call socket."""
import asyncio
import base64
import hashlib
import json
import logging
import re
import ssl
import time
import traceback
import uuid

from src.adapters.voice_output import TTSError


def observed_connector(emit):
    """Use websockets' normal verified transport; never log its headers/frames.

    asyncio.create_connection combines DNS/TCP/TLS. Don't invent their separate
    timestamps or replace the resolver/socket strategy merely for telemetry.
    """
    from websockets.asyncio.client import ClientConnection, connect

    class Connection(ClientConnection):
        async def handshake(self, *args, **kwargs):
            emit('http_upgrade_started')
            try:
                await super().handshake(*args, **kwargs)
            except BaseException:
                emit('http_upgrade_failed', http_status=getattr(self.response, 'status_code', None))
                raise
            emit('http_upgrade_complete', http_status=self.response.status_code)

    class Connect(connect):
        async def create_connection(self):
            emit('transport_connect_started', DNS='UNKNOWN', TCP='UNKNOWN', TLS_start='UNKNOWN')
            connection = await super().create_connection()
            tls = connection.transport.get_extra_info('ssl_object')
            if tls is None or not tls.context.check_hostname or tls.context.verify_mode != ssl.CERT_REQUIRED:
                connection.transport.abort()
                raise ValueError('VERIFIED_TLS_REQUIRED')
            emit('tls_verified_transport_ready', certificate_verified=True, hostname_verified=True,
                 TLS_version=tls.version(), certificate_sha256=hashlib.sha256(tls.getpeercert(binary_form=True)).hexdigest(),
                 peer_address=connection.transport.get_extra_info('peername'),
                 DNS_duration_ms='UNKNOWN', TCP_duration_ms='UNKNOWN', TLS_duration_ms='UNKNOWN')
            return connection

        def process_redirect(self, exc):
            # No additional endpoints, retries or credential-bearing redirects.
            return exc

    def factory(url, **kwargs):
        return Connect(url, create_connection=Connection, **kwargs)
    return factory


class QwenRealtimeVoiceOutput:
    def __init__(self, configuration, *, observer=None, audio_observer=None, connector=None):
        if (configuration.get('provider') != 'qwen_beijing'
                or configuration.get('model') != 'qwen3-tts-flash-realtime'
                or configuration.get('voice') != 'Kiki'
                or configuration.get('language_type') != 'Auto'
                or configuration.get('sample_rate') != 16000
                or configuration.get('completion_seconds') != 20
                or configuration.get('connect_seconds') != 5):
            raise ValueError('QWEN_TTS_CAPABILITY_CONFIGURATION_MISMATCH')
        self.configuration = configuration
        self.observer, self.audio_observer = observer, audio_observer
        self.connector = connector
        self.reuse = configuration.get('reuse_session', False)
        self.active = None
        self.closed = self._unusable = self._busy = False
        self._manager = self._reader = self._messages = None
        self._connection_id = self._session = self._last_state = None
        self._completed_responses = set()
        self._prepared_attempt = None
        self._closing_task = None

    async def prepare(self, state):
        """One owned Call: verified socket + fixed session only, no text/audio."""
        from src.adapters.voice_call_budget import charge
        if self.closed or self._busy or self.active is not None or self._unusable:
            raise RuntimeError('QWEN_PREPARATION_LIFECYCLE_INVALID')
        state.update(adapter_request_id=uuid.uuid4().hex,_started=time.monotonic(),
            provider='qwen_beijing',requested_model=self.configuration['model'],provider_complete=False)
        self._last_state=state
        charge('TTS','qwen_beijing',self.configuration['model'])
        self.event(state,'preparation_started',text_submitted=False,budget_seconds=5)
        try:
            async with asyncio.timeout(5):
                await self._ensure_connection(state)
            self.event(state,'preparation_ready',text_submitted=False)
            self._prepared_attempt=state
        except BaseException as exc:
            self._unusable=True;self._error(state,exc)
            await self._close_connection(state,normal=False)
            self.event(state,'preparation_failed',error_type=type(exc).__name__,text_submitted=False)
            raise

    def event(self, state, stage, **details):
        if stage == 'transport_connect_started':
            state['phase'] = 'transport_DNS_TCP_TLS'
        elif stage == 'http_upgrade_started':
            state['phase'] = 'http_upgrade'
        row = {'stage': stage, 'request_id': state['adapter_request_id'],
               'elapsed_ms': round((time.monotonic()-state['_started'])*1000, 3),
               'monotonic_ns': time.monotonic_ns(), 'provider': 'qwen_beijing',
               'socket_id': self._connection_id, **details}
        state.setdefault('events', []).append(row)
        if self.observer:
            try: self.observer(row)
            except Exception: pass
        return row['elapsed_ms']

    def _safe(self, value, length=400):
        value = str(value).replace(self.configuration['api_key'], '[REDACTED]')
        value = re.sub(r'(?i)(bearer\s+|authorization\s*[:=]\s*)\S+', '[REDACTED_AUTH]', value)
        value = re.sub(r'(?:https?|wss?)://\S+', '[REDACTED_URL]', value)
        return value[:length]

    def _error(self, state, exc):
        chain = []; current = exc
        while current is not None and len(chain) < 4:
            chain.append({'type': type(current).__name__, 'message': self._safe(current),
                          'errno': getattr(current, 'errno', None)})
            current = current.__cause__
        self.event(state, 'request_error', error_type=type(exc).__name__,
                   error_code=self._safe(getattr(exc, 'code', 'UNKNOWN'), 100),
                   phase=state.get('phase', 'UNKNOWN'), exception_chain=chain,
                   close_code=getattr(self.active, 'close_code', None),
                   stack=[{'file': f.filename.rsplit('/', 1)[-1], 'function': f.name, 'line': f.lineno}
                          for f in traceback.extract_tb(exc.__traceback__)[-10:]])

    async def _read(self):
        # Only this task calls recv. No user/segment context or logging is held
        # here; the active producer validates response IDs before consuming PCM.
        try:
            async for message in self.active:
                payload = json.loads(message)
                await self._messages.put((payload, time.monotonic_ns()))
            await self._messages.put((EOFError('QWEN_SOCKET_EOF'), time.monotonic_ns()))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await self._messages.put((exc, time.monotonic_ns()))

    async def _next(self):
        payload, received_ns = await self._messages.get()
        if isinstance(payload, BaseException): raise payload
        return payload, received_ns

    async def _send(self, state, kind, **extra):
        event_id = uuid.uuid4().hex
        await self.active.send(json.dumps({'type': kind, 'event_id': event_id, **extra}, ensure_ascii=False))
        self.event(state, kind+'_sent', event_id=event_id)

    async def _ensure_connection(self, state):
        if self._unusable: raise RuntimeError('QWEN_CONNECTION_INVALIDATED_NO_AUTO_RECONNECT')
        if self.active is not None:
            if self._reader.done(): raise RuntimeError('QWEN_READER_ENDED_NO_AUTO_RECONNECT')
            self.event(state, 'connection_reused', provider_session_id=self._session.get('id', 'UNKNOWN'))
            state['response_model'] = self._session.get('model', 'UNKNOWN')
            return
        state['phase'] = 'connection_open'
        self._connection_id = uuid.uuid4().hex
        self.event(state, 'connection_task_started', open_timeout_seconds=5)
        logger = logging.Logger('vefin-private-qwen-tts'); logger.disabled = True
        connect = self.connector or observed_connector(lambda stage, **details: self.event(state, stage, **details))
        self._manager = connect(
            'wss://dashscope.aliyuncs.com/api-ws/v1/realtime?model='+self.configuration['model'],
            additional_headers={'Authorization': 'Bearer '+self.configuration['api_key']},
            ssl=self.configuration.get('_ssl_context') or ssl.create_default_context(), proxy=None, open_timeout=5,
            close_timeout=1, max_size=2_000_000, logger=logger)
        self.active = await self._manager.__aenter__()
        state['connection_complete_ms'] = self.event(state, 'connection_complete', verify=True, proxy=None)
        self._messages = asyncio.Queue(maxsize=8)
        self._reader = asyncio.create_task(self._read())
        state['phase'] = 'session_initialization'
        while True:
            payload, received_ns = await self._next(); kind = payload.get('type')
            if kind == 'error': self._provider_error(state, payload)
            if kind == 'session.created':
                self._session = payload['session']
                state['response_model'] = self._session.get('model', 'UNKNOWN')
                self.event(state, 'session.created', received_monotonic_ns=received_ns,
                           provider_session_id=self._session.get('id', 'UNKNOWN'))
                await self._send(state, 'session.update', session={'voice': 'Kiki', 'mode': 'commit',
                    'response_format': 'pcm', 'sample_rate': 16000, 'language_type': 'Auto'})
            elif kind == 'session.updated':
                session = payload['session']
                if (session.get('voice') != 'Kiki' or session.get('sample_rate') != 16000
                        or session.get('response_format') != 'pcm'):
                    raise TTSError('UNSUPPORTED_EFFECTIVE_AUDIO_FORMAT', request_id=state['adapter_request_id'])
                state['effective_session'] = {k: session.get(k) for k in
                    ['voice', 'mode', 'model', 'sample_rate', 'response_format', 'language_type']}
                self.event(state, 'session.updated', received_monotonic_ns=received_ns, **state['effective_session'])
                return

    def _provider_error(self, state, payload):
        err = payload.get('error') or {}
        state['provider_error'] = {'code': self._safe(err.get('code', 'UNKNOWN'), 100),
                                   'message': self._safe(err.get('message', 'UNKNOWN'))}
        self.event(state, 'provider_error', **state['provider_error'])
        raise TTSError('UPSTREAM_REJECTED', request_id=state['adapter_request_id'])

    async def produce(self, text, language, state, queue):
        from src.adapters.voice_call_budget import charge
        if self.closed: raise RuntimeError('TTS_ADAPTER_CLOSED')
        if self._busy: raise RuntimeError('QWEN_CONCURRENT_SEGMENTS_UNSUPPORTED')
        if language != 'yue-HK': raise ValueError('QWEN_KIKI_SESSION_LANGUAGE_UNSUPPORTED')
        self._busy = True
        prepared=self._prepared_attempt;self._prepared_attempt=None
        if prepared:state.update(prepared)
        state.update(adapter_request_id=prepared['adapter_request_id'] if prepared else uuid.uuid4().hex,
            _started=prepared['_started'] if prepared else time.monotonic(),
            provider='qwen_beijing', requested_model=self.configuration['model'], voice='Kiki',
            language_control='Kiki documented Cantonese voice + language_type Auto; no GPT instructions',
            input_sha256=hashlib.sha256(text.encode()).hexdigest(), provider_complete=False)
        self._last_state = state
        raw = bytearray(); carry = b''; prefix = bytearray(); heard = audio_done = False
        response_id = output_item_id = None
        try:
            if not prepared:charge('TTS', 'qwen_beijing', self.configuration['model'])
            self.event(state, 'request_started',attempt_precharged_in_preparation=bool(prepared),
                timing_origin='CALL_PREPARATION' if prepared else 'TEXT_REQUEST')
            async with asyncio.timeout_at(state['_started']+20):
                await self._ensure_connection(state)
                await self._send(state, 'input_text_buffer.append', text=text)
                await self._send(state, 'input_text_buffer.commit')
                state['phase'] = 'submitted_waiting_response'
                self.event(state, 'text_committed', characters=len(text))
                while True:
                    payload, received_ns = await self._next(); kind = payload.get('type')
                    if 'first_response_event_ms' not in state:
                        state['first_response_event_ms'] = self.event(state, 'first_response_event', event_type=kind)
                    if kind == 'error': self._provider_error(state, payload)
                    rid = payload.get('response_id') or (payload.get('response') or {}).get('id')
                    if rid and rid in self._completed_responses:
                        self.event(state, 'stale_response_discarded', response_id=rid, event_type=kind)
                        continue
                    if kind == 'input_text_buffer.committed':
                        self.event(state, kind, item_id=payload.get('item_id', 'UNKNOWN'), received_monotonic_ns=received_ns)
                    elif kind == 'response.created':
                        if response_id or not rid: raise RuntimeError('QWEN_RESPONSE_ID_CONFLICT')
                        response_id = rid; state['phase'] = 'generating'
                        self.event(state, kind, response_id=rid, received_monotonic_ns=received_ns)
                    elif kind in {'response.audio.delta', 'response.audio.done', 'response.done'}:
                        if self.reuse and (not response_id or rid != response_id):
                            raise RuntimeError('QWEN_RESPONSE_ID_MISMATCH')
                        if kind != 'response.done':
                            item = payload.get('item_id')
                            if output_item_id and item != output_item_id: raise RuntimeError('QWEN_OUTPUT_ITEM_ID_MISMATCH')
                            output_item_id = item
                        if kind == 'response.audio.delta':
                            chunk = base64.b64decode(payload.get('delta', ''), validate=True)
                            if chunk and 'first_audio_byte_ms' not in state:
                                state['first_audio_byte_ms'] = self.event(state, 'first_audio_byte', bytes=len(chunk),
                                    response_id=rid or 'UNKNOWN', item_id=output_item_id or 'UNKNOWN', received_monotonic_ns=received_ns)
                            raw.extend(chunk)
                            if len(raw) > 24*1024*1024: raise TTSError('AUDIO_LIMIT', request_id=state['adapter_request_id'])
                            data = carry+chunk; usable = len(data)&~1; carry = data[usable:]; pcm = data[:usable]
                            if not heard:
                                prefix.extend(pcm)
                                import array
                                if not any(abs(v) > 8 for v in array.array('h', prefix)): continue
                                heard = True; pcm = bytes(prefix); prefix.clear()
                                state['first_valid_pcm_ms'] = self.event(state, 'first_valid_pcm', bytes=len(pcm), response_id=rid or 'UNKNOWN')
                            if pcm:
                                state['queued_pcm_bytes'] = state.get('queued_pcm_bytes', 0)+len(pcm)
                                state['peak_queued_pcm_bytes'] = max(state.get('peak_queued_pcm_bytes', 0), state['queued_pcm_bytes'])
                                queue.put_nowait(pcm)
                        elif kind == 'response.audio.done':
                            audio_done = True
                            self.event(state, kind, response_id=rid or 'UNKNOWN', item_id=output_item_id or 'UNKNOWN')
                        else:
                            response = payload.get('response') or {}
                            state['usage'] = response.get('usage'); state['provider_request_id'] = response.get('id')
                            if response.get('status') != 'completed' or not audio_done or carry or not heard:
                                raise TTSError('INCOMPLETE_AUDIO', request_id=state['adapter_request_id'])
                            state['provider_complete'] = True
                            self._completed_responses.add(state['provider_request_id'])
                            self.event(state, 'response.done', response_id=state['provider_request_id'], usage=state['usage'])
                            state['synthesis_complete_ms'] = self.event(state, 'synthesis_complete', pcm_bytes=len(raw),
                                pcm_sha256=hashlib.sha256(raw).hexdigest(), usage=state['usage'],
                                provider_request_id=state['provider_request_id'], response_model=state.get('response_model', 'UNKNOWN'))
                            break
        except asyncio.CancelledError as exc:
            state['cancelled'] = True; self._unusable = True; self._error(state, exc); raise
        except Exception as exc:
            state['error'] = getattr(exc, 'code', type(exc).__name__)
            self._unusable = True; self._error(state, exc); raise
        finally:
            if self._unusable or not self.reuse:
                await self._close_connection(state, normal=not self._unusable)
            if self.audio_observer and raw:
                try: self.audio_observer(bytes(raw), encoding='pcm_s16le', request_id=state['adapter_request_id'],
                    provider='qwen_beijing', sample_rate=16000, requested_model=self.configuration['model'],
                    provider_complete=state['provider_complete'])
                except Exception: pass
            state['source_pcm_sha256'] = hashlib.sha256(raw).hexdigest(); state['source_pcm_bytes'] = len(raw)
            state['duration_s'] = len(raw)/32000
            self.event(state, 'request_finished', provider_complete=state['provider_complete'],
                peak_queued_pcm_bytes=state.get('peak_queued_pcm_bytes', 0), queued_pcm_bytes=state.get('queued_pcm_bytes', 0))
            self._busy = False
            # Keep monotonic origin for final same-answer session cleanup events.

    async def _close_connection(self, state, *, normal):
        # Barge-in may cancel the caller while it is already closing an answer.
        # Join the owned cleanup before exposing a new answer boundary. Never
        # leave a cancelled __aexit__ with live reader/manager references.
        if self._closing_task is None:
            self._closing_task = asyncio.create_task(self._close_connection_owned(state, normal=normal))
        task = self._closing_task
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            await asyncio.shield(task)
            raise
        finally:
            if task.done() and self._closing_task is task:
                self._closing_task = None

    async def _close_connection_owned(self, state, *, normal):
        if self._manager is None: return
        self.event(state, 'connection_close_started', normal=normal)
        try:
            if normal and self.active:
                async with asyncio.timeout(1):
                    await self._send(state, 'session.finish')
                    while True:
                        payload, received_ns = await self._next()
                        if payload.get('type') == 'session.finished':
                            self.event(state, 'session.finished', received_monotonic_ns=received_ns); break
                        self.event(state, 'post_response_event_discarded', event_type=self._safe(payload.get('type'), 80))
        except Exception as exc:
            self.event(state, 'session_finish_cleanup_error', error_type=type(exc).__name__, message=self._safe(exc))
        finally:
            if self._reader:
                self._reader.cancel(); await asyncio.gather(self._reader, return_exceptions=True)
            try:
                async with asyncio.timeout(1.5):
                    await self._manager.__aexit__(None, None, None)
            except Exception as exc:
                self.event(state, 'connection_close_error', error_type=type(exc).__name__, message=self._safe(exc))
                transport = getattr(self.active, 'transport', None)
                if transport is not None:
                    transport.abort()
            self.event(state, 'connection_closed', close_code=getattr(self.active, 'close_code', None),
                       close_reason=self._safe(getattr(self.active, 'close_reason', None)))
            self.active = self._manager = self._reader = self._messages = None
            self._session = None; self._completed_responses.clear()

    async def finish_response(self):
        if self._last_state:
            await self._close_connection(self._last_state, normal=not self._unusable)

    async def begin_response(self):
        # A cancelled socket is never reused. Only an explicit *new answer*
        # after joined cleanup may create a new socket on its first request.
        if self.closed or self._busy or self.active is not None or self._reader is not None:
            raise RuntimeError('QWEN_NEW_RESPONSE_BEFORE_CLEANUP')
        self._unusable = False
        self._prepared_attempt = self._last_state = None
        self._completed_responses.clear()

    async def stream(self, text, *, language, state=None):
        state = state if state is not None else {}; queue = asyncio.Queue(); pending = None
        task = asyncio.create_task(self.produce(text, language, state, queue))
        try:
            while True:
                if task.done() and queue.empty():
                    await task; state['complete'] = True; break
                pending = asyncio.create_task(queue.get())
                ready, _ = await asyncio.wait({task, pending}, return_when=asyncio.FIRST_COMPLETED)
                if pending in ready:
                    pcm = pending.result(); pending = None
                    state['queued_pcm_bytes'] = state.get('queued_pcm_bytes', 0)-len(pcm)
                    yield pcm, 16000
                else:
                    pending.cancel(); await asyncio.gather(pending, return_exceptions=True); pending = None
                    await task
        finally:
            if pending: pending.cancel(); await asyncio.gather(pending, return_exceptions=True)
            if not task.done(): task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            if not state.get('complete'):
                self._unusable = True
                await self.finish_response()

    async def aclose(self):
        await self.finish_response()
        self.closed = True
