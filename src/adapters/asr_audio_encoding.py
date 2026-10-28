"""Documented ASR wire formats over unchanged mono 16k s16le input.

Only encoding: no filtering, normalization, trimming, gain, or tempo changes.
Opus is lossy; the original PCM hash and codec settings remain observable.
"""
import hashlib
import io
from fractions import Fraction


def encode_asr_pcm(pcm, *, wire_format, bitrate=16000):
    import av
    import numpy as np
    if not pcm or len(pcm) % 2 or wire_format not in {'flac','opus'}:
        raise ValueError('ASR_WIRE_FORMAT_INVALID')
    if wire_format == 'opus' and bitrate not in {12000,16000}:
        raise ValueError('ASR_WIRE_BITRATE_UNSUPPORTED')
    output = io.BytesIO()
    codec = 'libopus' if wire_format == 'opus' else 'flac'
    options = {'application':'voip','vbr':'on','frame_duration':'20'} if wire_format == 'opus' else {}
    with av.open(output, 'w', format='ogg' if wire_format == 'opus' else 'flac') as container:
        stream = container.add_stream(codec, rate=16000)
        stream.layout = 'mono'
        if wire_format == 'opus':
            stream.bit_rate = bitrate
            stream.codec_context.options = options.copy()
        frame = av.AudioFrame.from_ndarray(np.frombuffer(pcm,dtype='<i2').reshape(1,-1),
                                          format='s16',layout='mono')
        frame.sample_rate=16000;frame.pts=0;frame.time_base=Fraction(1,16000)
        for packet in stream.encode(frame):
            container.mux(packet)
        for packet in stream.encode(None):
            container.mux(packet)
        if stream.codec_context.options:
            raise ValueError('ASR_CODEC_OPTIONS_NOT_APPLIED')
    encoded=output.getvalue()
    return encoded, {
        'wire_format':wire_format,'wire_codec':codec,
        'wire_mime':'audio/ogg' if wire_format=='opus' else 'audio/flac',
        'wire_bitrate_target':bitrate if wire_format=='opus' else None,
        'wire_codec_options':options,'lossy':wire_format=='opus',
        'input_pcm_sha256':hashlib.sha256(pcm).hexdigest(),
        'input_pcm_bytes':len(pcm),'input_sample_rate':16000,'input_channels':1,
        'input_duration_seconds':len(pcm)/32000,
        'wire_bytes':len(encoded),'wire_sha256':hashlib.sha256(encoded).hexdigest(),
    }
