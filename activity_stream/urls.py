from django.conf.urls import patterns, url
from django.contrib.auth.decorators import login_required
from .views import ActivityStream, ActivityStreamSettings

urlpatterns = patterns('activity_stream.views',
    url(r'^$', ActivityStream.as_view(), name='activity_stream'),
    url(r'^settings/$', login_required(ActivityStreamSettings.as_view()),
        name='activity_stream_settings'),
)
