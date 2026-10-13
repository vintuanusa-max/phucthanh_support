"""Các kênh nhắn tin. Mỗi kênh là một module có cùng giao diện (xem channels/base.py)."""
from channels import whatsapp_wpp, zalo_web

CHANNELS = {zalo_web.NAME: zalo_web, whatsapp_wpp.NAME: whatsapp_wpp}


def start_all():
    for channel in CHANNELS.values():
        channel.start()
