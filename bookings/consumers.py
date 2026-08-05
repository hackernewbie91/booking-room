import json
from channels.generic.websocket import AsyncWebsocketConsumer

class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        if self.scope["user"].is_authenticated:
            self.group_name = f"user_{self.scope['user'].id}"
            await self.channel_layer.group_add(self.group_name, self.channel_name)
            await self.accept()
            
            # Kirim notifikasi yang belum dibaca saat connect
            from bookings.models import Notification
            from asgiref.sync import sync_to_async
            
            notifications = await sync_to_async(list)(
                Notification.objects.filter(user=self.scope['user'], is_read=False).order_by('-created_at')[:10]
            )
            
            unread_count = await sync_to_async(
                Notification.objects.filter(user=self.scope['user'], is_read=False).count
            )()
            
            data = {
                'notifications': [
                    {
                        'id': n.id,
                        'message': n.message,
                        'created_at': n.created_at.strftime('%d/%m %H:%M'),
                        'is_read': n.is_read
                    } for n in notifications
                ],
                'unread_count': unread_count
            }
            
            await self.send(text_data=json.dumps(data))
        else:
            await self.close()

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def send_notification(self, event):
        await self.send(text_data=json.dumps(event['data']))

    async def receive(self, text_data):
        data = json.loads(text_data)
        if data.get('action') == 'mark_read':
            from bookings.models import Notification
            from asgiref.sync import sync_to_async
            
            notif_id = data.get('notif_id')
            if notif_id:
                await sync_to_async(Notification.objects.filter(id=notif_id, user=self.scope['user']).update)(is_read=True)
            
            unread_count = await sync_to_async(
                Notification.objects.filter(user=self.scope['user'], is_read=False).count
            )()
            
            await self.send(text_data=json.dumps({'unread_count': unread_count}))
