from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from .models import SupportConversation
from .support import conversation_group, visitor_key_for_scope


class VisitorSupportConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.public_id = self.scope["url_route"]["kwargs"]["public_id"]
        visitor_key = visitor_key_for_scope(self.scope)
        if not visitor_key or not await self._authorized(visitor_key):
            await self.close(code=4403)
            return
        self.group_name = conversation_group(self.public_id)
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.send_json({"kind": "connected"})

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        # Messages are deliberately accepted only through the CSRF-protected
        # HTTP endpoint. WebSockets are a read-only live delivery channel.
        await self.send_json({"kind": "error", "message": "Send messages using the chat form."})

    async def support_event(self, event):
        await self.send_json(event["event"])

    @database_sync_to_async
    def _authorized(self, visitor_key):
        return SupportConversation.objects.filter(public_id=self.public_id, visitor_key=visitor_key).exists()


class StaffSupportConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        allowed = bool(
            user
            and user.is_authenticated
            and user.is_active
            and user.is_staff
            and await self._has_permission(user)
        )
        if not allowed:
            await self.close(code=4403)
            return
        self.group_name = "ivory_support_staff"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.send_json({"kind": "connected"})

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        await self.send_json({"kind": "error", "message": "Use the protected support controls."})

    async def support_event(self, event):
        await self.send_json(event["event"])

    @database_sync_to_async
    def _has_permission(self, user):
        return user.has_perm("Ivory.view_supportconversation")
