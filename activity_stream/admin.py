from django.contrib import admin
from models import Stream, StreamItem, StreamConnection


class StreamAdmin(admin.ModelAdmin):
    list_display = ('user',)
    search_fields = ['user']


class StreamItemAdmin(admin.ModelAdmin):
    list_display = ('source_id', 'title', 'type', 'connection', 'date', 'is_published', 'is_active')
    list_filter = ['connection__provider', 'type', 'is_published', 'is_active']
    date_hierarchy = 'date'
    search_fields = ['username', 'title', 'body', 'text']


class StreamConnectionAdmin(admin.ModelAdmin):
    list_display = ('stream', 'connection', 'post_delay_hours', 'stream_refresh_hours', 'updated',
                    'created', 'is_published')
    date_hierarchy = 'created'


admin.site.register(Stream, StreamAdmin)
admin.site.register(StreamItem, StreamItemAdmin)
admin.site.register(StreamConnection, StreamConnectionAdmin)
