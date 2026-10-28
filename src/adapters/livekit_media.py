"""Lazy SDK boundary: existing FastAPI deployments do not require voice packages."""

import os
from datetime import UTC, datetime, timedelta

from src.application.errors import ApplicationError


class LiveKitMedia:
    def __init__(self) -> None:
        self.url = os.getenv("LIVEKIT_URL", "http://127.0.0.1:7880")
        self.public_url = os.getenv("LIVEKIT_PUBLIC_URL", "ws://127.0.0.1:7880")
        self.key = os.getenv("LIVEKIT_API_KEY", "")
        self.secret = os.getenv("LIVEKIT_API_SECRET", "")

    @property
    def configured(self) -> bool:
        return bool(self.key and self.secret)

    def token(self, room: str, identity: str, expires_at: datetime) -> str:
        if not self.configured:
            raise ApplicationError("VOICE_MEDIA_UNAVAILABLE", "LiveKit 未配置。", status_code=503)
        from livekit import api

        ttl = expires_at - datetime.now(UTC)
        if ttl.total_seconds() <= 0:
            raise ApplicationError("VOICE_EXPIRED", "语音通话已到期。", status_code=410)
        return (api.AccessToken(self.key, self.secret).with_identity(identity)
                .with_ttl(min(ttl, timedelta(seconds=60)))
                .with_grants(api.VideoGrants(
                    room_join=True, room=room, can_publish=True, can_subscribe=True,
                    can_publish_data=False, can_publish_sources=["microphone"],
                )).to_jwt())

    async def delete_room(self, room: str) -> None:
        if not self.configured:
            return
        from aiohttp import ClientTimeout
        from livekit import api

        async with api.LiveKitAPI(self.url, self.key, self.secret,
                                  timeout=ClientTimeout(total=3)) as client:
            try:
                await client.room.delete_room(api.DeleteRoomRequest(room=room))
            except api.TwirpError as exc:
                if exc.code != "not_found":
                    raise

    async def room_names(self) -> set[str]:
        """One inventory read avoids repeated delete calls against historical absent rooms."""
        if not self.configured:
            return set()
        from aiohttp import ClientTimeout
        from livekit import api

        async with api.LiveKitAPI(self.url, self.key, self.secret,
                                  timeout=ClientTimeout(total=3)) as client:
            rooms = await client.room.list_rooms(api.ListRoomsRequest())
        return {room.name for room in rooms.rooms}

    async def retire_previous_agents(self, room: str, current_identity: str) -> None:
        """Fenced replacement removes only obsolete agents in this session's room."""
        if not self.configured:
            return
        from aiohttp import ClientTimeout
        from livekit import api

        async with api.LiveKitAPI(self.url, self.key, self.secret,
                                  timeout=ClientTimeout(total=3)) as client:
            try:
                participants = await client.room.list_participants(
                    api.ListParticipantsRequest(room=room)
                )
                for participant in participants.participants:
                    if (participant.identity.startswith("agent:")
                            and participant.identity != current_identity):
                        await client.room.remove_participant(api.RoomParticipantIdentity(
                            room=room, identity=participant.identity,
                        ))
            except api.TwirpError as exc:
                if exc.code != "not_found":
                    raise

    async def healthy(self) -> bool:
        if not self.configured:
            return False
        from aiohttp import ClientTimeout
        from livekit import api

        async with api.LiveKitAPI(self.url, self.key, self.secret,
                                  timeout=ClientTimeout(total=3)) as client:
            await client.room.list_rooms(api.ListRoomsRequest())
        return True
