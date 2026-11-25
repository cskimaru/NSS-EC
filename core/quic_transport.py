"""
QUIC Transport Layer for NSS-EC
Cryptographically Sovereign Multi-Cloud Storage

Provides an alternative to boto3/S3 HTTP for uploading and downloading shards.
QUIC (RFC 9000) eliminates the TCP RTO cliff by design:
  - UDP-based: no connection window resets on idle
  - Independent streams: one stream stall does not block others
  - TLS 1.3 built-in: no separate TLS handshake overhead
  - Faster recovery: QUIC uses ACK-based loss detection, not timeout-based

Usage:
    from core.quic_transport import QUICClient
    client = QUICClient(host="127.0.0.1", port=14433)
    await client.upload(key, data)
    data = await client.download(key)

Requirements:
    pip install aioquic>=1.0.0

The QUIC server counterpart should be deployed alongside SeaweedFS.
See infra/quic_server.py for a reference asyncio server.

Author: Noah Kimaru | Kyoto Institute of Technology | 2026
"""

import asyncio
import ssl
import os
from typing import Optional

try:
    from aioquic.asyncio import connect
    from aioquic.asyncio.protocol import QuicConnectionProtocol
    from aioquic.quic.configuration import QuicConfiguration
    from aioquic.quic.events import StreamDataReceived, HandshakeCompleted
    HAS_QUIC = True
except ImportError:
    HAS_QUIC = False


class QUICUploadProtocol(QuicConnectionProtocol if HAS_QUIC else object):
    """Simple request-response QUIC protocol for shard upload/download."""

    def __init__(self, *args, **kwargs):
        if HAS_QUIC:
            super().__init__(*args, **kwargs)
        self._responses: dict[int, bytearray] = {}
        self._futures: dict[int, asyncio.Future] = {}

    def quic_event_received(self, event):
        if isinstance(event, StreamDataReceived):
            sid = event.stream_id
            if sid not in self._responses:
                self._responses[sid] = bytearray()
            self._responses[sid].extend(event.data)
            if event.end_stream:
                fut = self._futures.pop(sid, None)
                if fut and not fut.done():
                    fut.set_result(bytes(self._responses.pop(sid)))

    async def _request(self, payload: bytes) -> bytes:
        """Send payload on a new stream, await response."""
        stream_id = self._quic.get_next_available_stream_id()
        fut = asyncio.get_event_loop().create_future()
        self._futures[stream_id] = fut
        self._quic.send_stream_data(stream_id, payload, end_stream=True)
        self.transmit()
        return await asyncio.wait_for(fut, timeout=30.0)

    async def upload(self, key: str, data: bytes) -> bool:
        """Upload key→data. Protocol: 4-byte key_len + key + data."""
        key_b = key.encode()
        payload = len(key_b).to_bytes(4, "big") + key_b + data
        resp = await self._request(b"PUT" + payload)
        return resp == b"OK"

    async def download(self, key: str) -> Optional[bytes]:
        """Download key. Protocol: 4-byte key_len + key."""
        key_b = key.encode()
        payload = len(key_b).to_bytes(4, "big") + key_b
        resp = await self._request(b"GET" + payload)
        if resp == b"NOT_FOUND":
            return None
        return resp


class QUICClient:
    """
    Async QUIC client for NSS-EC shard storage.

    Replace SeaweedFS S3 calls with this for QUIC transport:
        - No TCP RTO: UDP streams, independent per-shard
        - TLS 1.3 built-in
        - Stream multiplexing: 9 shard uploads in parallel streams

    Example:
        async with QUICClient("127.0.0.1", 14433) as client:
            await client.upload("file_id/shard_0", shard_bytes)
            data = await client.download("file_id/shard_0")
    """

    def __init__(self, host: str, port: int, verify_tls: bool = True,
                 cafile: Optional[str] = None):
        if not HAS_QUIC:
            raise ImportError("aioquic is required: pip install aioquic>=1.0.0")
        self.host = host
        self.port = port
        self.verify_tls = verify_tls
        self.cafile = cafile
        self._protocol: Optional[QUICUploadProtocol] = None

    async def __aenter__(self):
        config = QuicConfiguration(is_client=True)
        if not self.verify_tls:
            config.verify_mode = ssl.CERT_NONE
        elif self.cafile:
            config.cafile = self.cafile

        self._cm = connect(
            self.host, self.port,
            configuration=config,
            create_protocol=QUICUploadProtocol,
        )
        self._protocol = await self._cm.__aenter__()
        return self

    async def __aexit__(self, *args):
        await self._cm.__aexit__(*args)

    async def upload(self, key: str, data: bytes) -> bool:
        return await self._protocol.upload(key, data)

    async def download(self, key: str) -> Optional[bytes]:
        return await self._protocol.download(key)

    async def upload_shards_parallel(self, file_id: str, shards: list[bytes],
                                      nonces: list[bytes]) -> None:
        """Upload all 9 shards as independent QUIC streams (true parallelism)."""
        tasks = []
        for i, (shard, nonce) in enumerate(zip(shards, nonces)):
            payload = nonce + shard  # prepend nonce like S3 path
            tasks.append(self.upload(f"{file_id}/shard_{i}", payload))
        results = await asyncio.gather(*tasks)
        if not all(results):
            raise RuntimeError("One or more shard uploads failed over QUIC")


def run_quic_upload(host: str, port: int, file_id: str,
                     shards: list[bytes], nonces: list[bytes]) -> None:
    """Synchronous wrapper for QUIC upload — drop-in for boto3 upload path."""
    async def _run():
        async with QUICClient(host, port, verify_tls=False) as client:
            await client.upload_shards_parallel(file_id, shards, nonces)
    asyncio.run(_run())
