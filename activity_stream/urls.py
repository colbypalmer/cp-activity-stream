from django.conf.urls import patterns, include, url
from .views import ActivityStream, ActivityStreamSettings

urlpatterns = patterns('activity_stream.views',
                       url(r'^$', ActivityStream.as_view(), name='activity_stream'),
                       url(r'^settings/$', ActivityStreamSettings.as_view(), name='activity_stream_settings'),
                       )
