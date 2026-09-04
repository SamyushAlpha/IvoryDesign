from django.urls import path

from .consumers import StaffSupportConsumer, VisitorSupportConsumer

websocket_urlpatterns = [
    path("ws/support/staff/", StaffSupportConsumer.as_asgi()),
    path("ws/support/<uuid:public_id>/", VisitorSupportConsumer.as_asgi()),
]
